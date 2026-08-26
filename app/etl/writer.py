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
from app.repository import tables as t
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
        # MHFU-ASS ships no Japanese names; fall back to English
        # (data-pack-spec.md ETL rule 2).
        tree_ids: dict[str, int] = {}
        tree_rows: list[dict[str, Any]] = []
        skill_rows: list[dict[str, Any]] = []
        for ordinal, block in enumerate(data.skill_trees, start=1):
            tree_id = base + ordinal
            tree_ids[block.name] = tree_id
            tree_rows.append({
                "id": tree_id, "game_id": game_id, "name_en": block.name,
                "name_ja": block.name, "category_tag": block.tag,
            })
            for points, skill_name in block.thresholds:
                skill_rows.append({
                    "id": base + len(skill_rows) + 1, "tree_id": tree_id,
                    "name_en": skill_name, "name_ja": skill_name,
                    "points": points, "is_negative": points < 0,
                })
        self._repo.bulk_insert(t.skill_trees, tree_rows)
        self._repo.bulk_insert(t.skills, skill_rows)
        counts["skill_trees"] = len(tree_rows)
        counts["skills"] = len(skill_rows)

        armor_rows: list[dict[str, Any]] = []
        armor_skill_rows: list[dict[str, Any]] = []
        for ordinal, row in enumerate(data.armor, start=1):
            piece_id = base + ordinal
            armor_rows.append({
                "id": piece_id, "game_id": game_id, "slot": row.slot,
                "name_en": row.name_en, "name_ja": row.name_en,
                "rarity": row.rarity, "slots": row.slots,
                "gender": row.gender, "hunter_type": row.hunter_type,
                "hr_required": row.hr_required, "village_stars": row.village_stars,
                "defense": row.defense, "max_defense": row.defense,
                "res_fire": row.res_fire, "res_water": row.res_water,
                "res_ice": row.res_ice, "res_thunder": row.res_thunder,
                "res_dragon": row.res_dragon, "torso_inc": row.torso_inc,
            })
            seen_trees: set[int] = set()
            for tree_name, points in row.skills:
                tree_id = tree_ids[tree_name]
                if tree_id in seen_trees:
                    # A piece listing a tree twice: legacy GetSkillAt returns the
                    # first match, so keep-first (armor_skills PK is (armor, tree)).
                    continue
                seen_trees.add(tree_id)
                armor_skill_rows.append({
                    "armor_id": piece_id, "tree_id": tree_id, "points": points,
                })
        self._repo.bulk_insert(t.armor_pieces, armor_rows)
        self._repo.bulk_insert(t.armor_skills, armor_skill_rows)
        counts["armor_pieces"] = len(armor_rows)
        counts["armor_skills"] = len(armor_skill_rows)

        deco_rows: list[dict[str, Any]] = []
        deco_skill_rows: list[dict[str, Any]] = []
        for ordinal, row in enumerate(data.decorations, start=1):
            deco_id = base + ordinal
            deco_rows.append({
                "id": deco_id, "game_id": game_id, "name_en": row.name_en,
                "name_ja": row.name_en,
                "rarity": 1,  # MHFU decorations.csv has no rarity column
                "size": row.size, "hr_required": row.hr_required,
            })
            for tree_name, points in row.skills:
                deco_skill_rows.append({
                    "decoration_id": deco_id, "tree_id": tree_ids[tree_name],
                    "points": points,
                })
        self._repo.bulk_insert(t.decorations, deco_rows)
        self._repo.bulk_insert(t.decoration_skills, deco_skill_rows)
        counts["decorations"] = len(deco_rows)
        counts["decoration_skills"] = len(deco_skill_rows)

        return counts

    def _clear_pack_data(self, manifest: PackManifest) -> int:
        """Delete the pack's game-data children (FK-safe bulk delete) and return
        the game id, reusing the existing `games` row when present so user-table
        references survive a rebuild."""
        repo = self._repo
        features = json.dumps(manifest.features, sort_keys=True)
        game = repo.get_game_by_code(manifest.id)
        if game is None:
            return repo.create_game(code=manifest.id, name=manifest.name,
                                    generation=manifest.generation,
                                    features=features)["id"]
        game_id = game["id"]
        repo.delete_game_data(game_id)
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
