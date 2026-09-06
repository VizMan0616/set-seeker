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

from app.etl.loaders import PackData, charm_point_union, torso_inc_skill_name
from app.etl.manifest import PackManifest
from app.repository import tables as t
from app.repository.game_data import GameDataRepository

ID_STRIDE = 1_000_000  # per-game id space within each game-data table


class PackWriter:
    def __init__(self, repo: GameDataRepository) -> None:
        self._repo = repo

    def rebuild_pack(self, manifest: PackManifest, data: PackData) -> dict[str, int]:
        game_id = self._clear_pack_data(manifest, data)
        base = game_id * ID_STRIDE
        counts: dict[str, int] = {"games": 1}

        # Skill trees + threshold rows. Tree ids are needed before armor/decos.
        # MHFU-ASS ships no Japanese names; fall back to English
        # (data-pack-spec.md ETL rule 2).
        tree_ids: dict[str, int] = {}
        tree_rows: list[dict[str, Any]] = []
        skill_rows: list[dict[str, Any]] = []
        tag_rows: list[dict[str, Any]] = []
        category_order: list[str] = []
        for ordinal, block in enumerate(data.skill_trees, start=1):
            tree_id = base + ordinal
            tree_ids[block.name] = tree_id
            tree_rows.append(
                {
                    "id": tree_id,
                    "game_id": game_id,
                    "name_en": block.name,
                    "name_ja": block.name_ja or block.name,
                    "category_tag": block.tag,
                }
            )
            for tag in block.tags:
                tag_rows.append({"tree_id": tree_id, "tag": tag})
                if tag not in category_order:
                    category_order.append(tag)
            for points, skill_name in block.thresholds:
                skill_rows.append(
                    {
                        "id": base + len(skill_rows) + 1,
                        "tree_id": tree_id,
                        "name_en": skill_name,
                        "name_ja": skill_name,
                        "points": points,
                        "is_negative": points < 0,
                    }
                )
        self._repo.bulk_insert(t.skill_trees, tree_rows)
        self._repo.bulk_insert(t.skills, skill_rows)
        self._repo.bulk_insert(t.skill_tree_tags, tag_rows)
        self._repo.bulk_insert(
            t.skill_categories,
            [
                {"game_id": game_id, "tag": tag, "sort_order": i}
                for i, tag in enumerate(category_order)
            ],
        )
        counts["skill_trees"] = len(tree_rows)
        counts["skills"] = len(skill_rows)
        counts["skill_tree_tags"] = len(tag_rows)
        counts["skill_categories"] = len(category_order)

        armor_rows: list[dict[str, Any]] = []
        armor_skill_rows: list[dict[str, Any]] = []
        for ordinal, row in enumerate(data.armor, start=1):
            piece_id = base + ordinal
            armor_rows.append(
                {
                    "id": piece_id,
                    "game_id": game_id,
                    "slot": row.slot,
                    "name_en": row.name_en,
                    "name_ja": row.name_ja or row.name_en,
                    "rarity": row.rarity,
                    "slots": row.slots,
                    "gender": row.gender,
                    "hunter_type": row.hunter_type,
                    "hr_required": row.hr_required,
                    "village_stars": row.village_stars,
                    "defense": row.defense,
                    "max_defense": row.max_defense if row.max_defense is not None else row.defense,
                    "res_fire": row.res_fire,
                    "res_water": row.res_water,
                    "res_ice": row.res_ice,
                    "res_thunder": row.res_thunder,
                    "res_dragon": row.res_dragon,
                    "torso_inc": row.torso_inc,
                    "is_dummy": row.is_dummy,
                }
            )
            seen_trees: set[int] = set()
            for tree_name, points in row.skills:
                tree_id = tree_ids[tree_name]
                if tree_id in seen_trees:
                    # A piece listing a tree twice: legacy GetSkillAt returns the
                    # first match, so keep-first (armor_skills PK is (armor, tree)).
                    continue
                seen_trees.add(tree_id)
                armor_skill_rows.append(
                    {
                        "armor_id": piece_id,
                        "tree_id": tree_id,
                        "points": points,
                    }
                )
        self._repo.bulk_insert(t.armor_pieces, armor_rows)
        self._repo.bulk_insert(t.armor_skills, armor_skill_rows)
        counts["armor_pieces"] = len(armor_rows)
        counts["armor_skills"] = len(armor_skill_rows)

        deco_rows: list[dict[str, Any]] = []
        deco_skill_rows: list[dict[str, Any]] = []
        for ordinal, row in enumerate(data.decorations, start=1):
            deco_id = base + ordinal
            deco_rows.append(
                {
                    "id": deco_id,
                    "game_id": game_id,
                    "name_en": row.name_en,
                    "name_ja": row.name_ja or row.name_en,
                    "rarity": row.rarity,
                    "size": row.size,
                    "hr_required": row.hr_required,
                    "village_stars": row.village_stars,
                }
            )
            for tree_name, points in row.skills:
                deco_skill_rows.append(
                    {
                        "decoration_id": deco_id,
                        "tree_id": tree_ids[tree_name],
                        "points": points,
                    }
                )
        self._repo.bulk_insert(t.decorations, deco_rows)
        self._repo.bulk_insert(t.decoration_skills, deco_skill_rows)
        counts["decorations"] = len(deco_rows)
        counts["decoration_skills"] = len(deco_skill_rows)

        charm_type_rows: list[dict[str, Any]] = []
        range_rows: list[dict[str, Any]] = []
        slot_rows: list[dict[str, Any]] = []
        for ordinal, charm in enumerate(data.charm_types, start=1):
            charm_id = base + ordinal
            charm_type_rows.append(
                {
                    "id": charm_id,
                    "game_id": game_id,
                    "code": charm.code,
                    "max_slots": charm.max_slots,
                }
            )
            for rng in charm.ranges:
                range_rows.append(
                    {
                        "charm_type_id": charm_id,
                        "tree_id": tree_ids[rng.tree],
                        "skill_slot": rng.skill_slot,
                        "min_points": rng.min_points,
                        "max_points": rng.max_points,
                    }
                )
            for fulfillment, slots in charm.slot_thresholds:
                slot_rows.append(
                    {
                        "charm_type_id": charm_id,
                        "fulfillment": fulfillment,
                        "slots": slots,
                    }
                )
        self._repo.bulk_insert(t.charm_types, charm_type_rows)
        self._repo.bulk_insert(t.charm_skill_ranges, range_rows)
        self._repo.bulk_insert(t.charm_slot_thresholds, slot_rows)
        counts["charm_types"] = len(charm_type_rows)
        counts["charm_skill_ranges"] = len(range_rows)
        counts["charm_slot_thresholds"] = len(slot_rows)

        return counts

    def _clear_pack_data(self, manifest: PackManifest, data: PackData) -> int:
        """Delete the pack's game-data children (FK-safe bulk delete) and return
        the game id, reusing the existing `games` row when present so user-table
        references survive a rebuild."""
        repo = self._repo
        extra = {}
        if manifest.translation:
            extra["translation"] = manifest.translation
        feature_blob = {
            **manifest.features,
            **extra,
            "guild_rank_max": manifest.progression["guild_rank"],
            "village_stars_max": manifest.progression["village_stars"],
            "desired_skills_max": manifest.desired_skills_max,
            "data_version": manifest.data_version,
        }
        union = charm_point_union(data.charm_types)
        if union:
            feature_blob["charm_points"] = union
        elif manifest.charm_points:
            feature_blob["charm_points"] = manifest.charm_points
        torso_name = torso_inc_skill_name(data)
        if torso_name:
            feature_blob["torso_inc_name"] = torso_name
        features = json.dumps(feature_blob, sort_keys=True)
        game = repo.get_game_by_code(manifest.id)
        if game is None:
            return repo.create_game(
                code=manifest.id,
                name=manifest.name,
                generation=manifest.generation,
                features=features,
            )["id"]
        game_id = game["id"]
        repo.delete_game_data(game_id)
        repo.update_game(
            game_id, name=manifest.name, generation=manifest.generation, features=features
        )
        return game_id


def rebuild_from_sources(
    repo: GameDataRepository, manifest: PackManifest, pack_data: PackData
) -> dict[str, int]:
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
    n_tags = 0
    for tree in repo.list_skill_trees(game_id):
        n_trees += 1
        n_skills += len(repo.list_skills_for_tree(tree["id"]))
        n_tags += len(repo.list_skill_tree_tags(tree["id"]))
    charm_types = repo.list_charm_types(game_id)
    n_ranges = 0
    n_slots = 0
    for charm in charm_types:
        n_ranges += len(repo.list_charm_skill_ranges(charm["id"]))
        n_slots += len(repo.list_charm_slot_thresholds(charm["id"]))
    return {
        "skill_trees": n_trees,
        "skills": n_skills,
        "skill_tree_tags": n_tags,
        "skill_categories": len(repo.list_skill_categories(game_id)),
        "armor_pieces": n_armor,
        "armor_skills": n_armor_skills,
        "decorations": n_decos,
        "decoration_skills": n_deco_skills,
        "charm_types": len(charm_types),
        "charm_skill_ranges": n_ranges,
        "charm_slot_thresholds": n_slots,
    }
