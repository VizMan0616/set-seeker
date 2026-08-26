"""Write parsed pack data into the schema via the repository layer.

Never raw SQL (ADR 0004); every row crosses `GameDataRepository`. A rebuild is
idempotent: it deletes the pack's existing game-data rows and re-inserts them.
User tables (`sessions`, `user_charms`, `search_states`) are never touched
(run-etl rule 2) — and because game-data ids are deterministic
(`game_id * 1_000_000 + ordinal`, per table) and the `games` row is reused,
foreign keys from `user_charms` keep pointing at live rows across rebuilds.
"""

import json
from typing import Any

from app.etl.loaders import PackData
from app.etl.manifest import PackManifest
from app.repository.game_data import GameDataRepository

ID_STRIDE = 1_000_000  # per-game id space within each game-data table


class PackWriter:
    def __init__(self, repo: GameDataRepository) -> None:
        self._repo = repo

    def rebuild_pack(self, manifest: PackManifest, data: PackData) -> dict[str, int]:
        game_id = self._clear_pack_data(manifest)
        base = game_id * ID_STRIDE
        counts: dict[str, int] = {"games": 1}

        # Skill trees + threshold rows. Tree ids are needed before armor/decos.
        tree_ids: dict[str, int] = {}
        n_skills = 0
        for ordinal, block in enumerate(data.skill_trees, start=1):
            # MHFU-ASS ships no Japanese names; fall back to English
            # (data-pack-spec.md ETL rule 2).
            tree = self._repo.create_skill_tree(
                id=base + ordinal,
                game_id=game_id, name_en=block.name, name_ja=block.name,
                category_tag=block.tag,
            )
            tree_ids[block.name] = tree["id"]
            for points, skill_name in block.thresholds:
                n_skills += 1
                self._repo.create_skill(
                    id=base + n_skills,
                    tree_id=tree["id"], name_en=skill_name, name_ja=skill_name,
                    points=points, is_negative=points < 0,
                )
        counts["skill_trees"] = len(tree_ids)
        counts["skills"] = n_skills

        n_armor_skills = 0
        for ordinal, row in enumerate(data.armor, start=1):
            piece = self._repo.create_armor_piece(
                id=base + ordinal,
                game_id=game_id, slot=row.slot, name_en=row.name_en,
                name_ja=row.name_en, rarity=row.rarity, slots=row.slots,
                gender=row.gender, hunter_type=row.hunter_type,
                hr_required=row.hr_required, village_stars=row.village_stars,
                defense=row.defense, max_defense=row.defense,
                res_fire=row.res_fire, res_water=row.res_water,
                res_ice=row.res_ice, res_thunder=row.res_thunder,
                res_dragon=row.res_dragon, torso_inc=row.torso_inc,
            )
            seen_trees: set[int] = set()
            for tree_name, points in row.skills:
                tree_id = tree_ids[tree_name]
                if tree_id in seen_trees:
                    # A piece listing a tree twice: legacy GetSkillAt returns the
                    # first match, so keep-first (armor_skills PK is (armor, tree)).
                    continue
                seen_trees.add(tree_id)
                self._repo.set_armor_skill(armor_id=piece["id"], tree_id=tree_id,
                                           points=points)
                n_armor_skills += 1
        counts["armor_pieces"] = len(data.armor)
        counts["armor_skills"] = n_armor_skills

        n_deco_skills = 0
        for ordinal, row in enumerate(data.decorations, start=1):
            deco = self._repo.create_decoration(
                id=base + ordinal,
                game_id=game_id, name_en=row.name_en, name_ja=row.name_en,
                rarity=1,  # MHFU decorations.csv has no rarity column
                size=row.size, hr_required=row.hr_required,
            )
            for tree_name, points in row.skills:
                self._repo.set_decoration_skill(decoration_id=deco["id"],
                                                tree_id=tree_ids[tree_name],
                                                points=points)
                n_deco_skills += 1
        counts["decorations"] = len(data.decorations)
        counts["decoration_skills"] = n_deco_skills

        return counts

    def _clear_pack_data(self, manifest: PackManifest) -> int:
        """Delete the pack's game-data children (FK-safe order) and return the
        game id, reusing the existing `games` row when present so user-table
        references survive a rebuild."""
        repo = self._repo
        features = json.dumps(manifest.features, sort_keys=True)
        game = repo.get_game_by_code(manifest.id)
        if game is None:
            return repo.create_game(code=manifest.id, name=manifest.name,
                                    generation=manifest.generation,
                                    features=features)["id"]
        game_id = game["id"]

        for piece in repo.list_armor_pieces(game_id, allow_event=True):
            for skill in repo.list_armor_skills_for_piece(piece["id"]):
                repo.delete_armor_skill(skill["armor_id"], skill["tree_id"])
            repo.delete_armor_piece(piece["id"])

        for deco in repo.list_decorations(game_id, allow_event=True):
            for skill in repo.list_decoration_skills_for_decoration(deco["id"]):
                repo.delete_decoration_skill(skill["decoration_id"], skill["tree_id"])
            repo.delete_decoration(deco["id"])

        for tree in repo.list_skill_trees(game_id):
            for skill in repo.list_skills_for_tree(tree["id"]):
                repo.delete_skill(skill["id"])
            repo.delete_skill_tree(tree["id"])

        for charm_type in repo.list_charm_types(game_id):
            for rng in repo.list_charm_skill_ranges(charm_type["id"]):
                repo.delete_charm_skill_range(rng["charm_type_id"], rng["tree_id"],
                                              rng["skill_slot"])
            for threshold in repo.list_charm_slot_thresholds(charm_type["id"]):
                repo.delete_charm_slot_threshold(threshold["charm_type_id"],
                                                 threshold["fulfillment"])
            repo.delete_charm_type(charm_type["id"])

        for entry in repo.list_mh3u_charm_table(game_id):
            repo.delete_mh3u_charm_table_entry(entry["id"])

        repo.update_game(game_id, name=manifest.name,
                         generation=manifest.generation, features=features)
        return game_id


def rebuild_from_sources(repo: GameDataRepository, manifest: PackManifest,
                         pack_data: PackData) -> dict[str, int]:
    return PackWriter(repo).rebuild_pack(manifest, pack_data)


def table_counts(repo: GameDataRepository, game_id: int) -> dict[str, Any]:
    """Row counts per game-data table for one pack (gate + reporting)."""
    n_armor = 0
    n_armor_skills = 0
    for piece in repo.list_armor_pieces(game_id, allow_event=True):
        n_armor += 1
        n_armor_skills += len(repo.list_armor_skills_for_piece(piece["id"]))
    n_decos = 0
    n_deco_skills = 0
    for deco in repo.list_decorations(game_id, allow_event=True):
        n_decos += 1
        n_deco_skills += len(repo.list_decoration_skills_for_decoration(deco["id"]))
    n_trees = 0
    n_skills = 0
    for tree in repo.list_skill_trees(game_id):
        n_trees += 1
        n_skills += len(repo.list_skills_for_tree(tree["id"]))
    return {
        "skill_trees": n_trees,
        "skills": n_skills,
        "armor_pieces": n_armor,
        "armor_skills": n_armor_skills,
        "decorations": n_decos,
        "decoration_skills": n_deco_skills,
    }
