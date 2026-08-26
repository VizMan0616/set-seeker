"""Game-data repository: the only DB seam for pack data (ADR 0004).

SQLAlchemy Core expression language only; rows cross the interface as plain
dicts so no SQLAlchemy objects leak into callers. All public methods are thin
domain-named wrappers over the private generic CRUD helpers.
"""

from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Engine

from app.repository import tables as t


class GameDataRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # --- private generic CRUD helpers ---

    def _create(self, table, values: dict[str, Any]) -> dict[str, Any]:
        with self._engine.begin() as conn:
            result = conn.execute(insert(table).values(**values))
            pk_values = result.inserted_primary_key or tuple(
                values[col.name] for col in table.primary_key
            )
            row = conn.execute(
                select(table).where(
                    *(col == val for col, val in zip(table.primary_key, pk_values, strict=True))
                )
            ).one()
            return dict(row._mapping)

    def _get(self, table, **pk) -> dict[str, Any] | None:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(table).where(*(table.c[k] == v for k, v in pk.items()))
            ).one_or_none()
            return dict(row._mapping) if row is not None else None

    def _list(self, table, *criteria, order_by=None) -> list[dict[str, Any]]:
        stmt = select(table).where(*criteria)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        with self._engine.begin() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).all()]

    def _update(self, table, pk: dict[str, Any], values: dict[str, Any]) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                update(table)
                .where(*(table.c[k] == v for k, v in pk.items()))
                .values(**values)
            )
            return result.rowcount > 0

    def _delete(self, table, **pk) -> bool:
        with self._engine.begin() as conn:
            result = conn.execute(
                delete(table).where(*(table.c[k] == v for k, v in pk.items()))
            )
            return result.rowcount > 0

    # --- bulk operations (ETL rebuild path) ---

    def bulk_insert(self, table, rows: list[dict[str, Any]]) -> None:
        """Multi-row insert in a single transaction (SQLAlchemy Core only)."""
        if not rows:
            return
        with self._engine.begin() as conn:
            conn.execute(insert(table), rows)

    def delete_game_data(self, game_id: int) -> None:
        """Delete every game-data child row for a pack in one transaction.

        FK-safe order (children before parents); the `games` row itself is
        kept so user-table references survive a rebuild. User tables
        (`sessions`, `user_charms`, `search_states`) are never touched.
        """
        c = t
        piece_ids = select(c.armor_pieces.c.id).where(c.armor_pieces.c.game_id == game_id)
        deco_ids = select(c.decorations.c.id).where(c.decorations.c.game_id == game_id)
        tree_ids = select(c.skill_trees.c.id).where(c.skill_trees.c.game_id == game_id)
        charm_type_ids = select(c.charm_types.c.id).where(c.charm_types.c.game_id == game_id)
        with self._engine.begin() as conn:
            conn.execute(delete(c.armor_skills).where(c.armor_skills.c.armor_id.in_(piece_ids)))
            conn.execute(
                delete(c.decoration_skills).where(c.decoration_skills.c.decoration_id.in_(deco_ids))
            )
            conn.execute(
                delete(c.charm_skill_ranges).where(
                    c.charm_skill_ranges.c.charm_type_id.in_(charm_type_ids)
                )
            )
            conn.execute(
                delete(c.charm_slot_thresholds).where(
                    c.charm_slot_thresholds.c.charm_type_id.in_(charm_type_ids)
                )
            )
            conn.execute(
                delete(c.mh3u_charm_tables).where(c.mh3u_charm_tables.c.game_id == game_id)
            )
            conn.execute(delete(c.skills).where(c.skills.c.tree_id.in_(tree_ids)))
            conn.execute(delete(c.armor_pieces).where(c.armor_pieces.c.game_id == game_id))
            conn.execute(delete(c.decorations).where(c.decorations.c.game_id == game_id))
            conn.execute(delete(c.skill_trees).where(c.skill_trees.c.game_id == game_id))
            conn.execute(delete(c.charm_types).where(c.charm_types.c.game_id == game_id))

    # --- games ---

    def create_game(self, *, code: str, name: str, generation: int, features: str,
                    **extra) -> dict[str, Any]:
        return self._create(t.games, dict(code=code, name=name, generation=generation,
                                          features=features, **extra))

    def get_game(self, game_id: int) -> dict[str, Any] | None:
        return self._get(t.games, id=game_id)

    def get_game_by_code(self, code: str) -> dict[str, Any] | None:
        rows = self._list(t.games, t.games.c.code == code)
        return rows[0] if rows else None

    def list_games(self) -> list[dict[str, Any]]:
        return self._list(t.games, order_by=t.games.c.generation)

    def update_game(self, game_id: int, **values) -> bool:
        return self._update(t.games, {"id": game_id}, values)

    def delete_game(self, game_id: int) -> bool:
        return self._delete(t.games, id=game_id)

    # --- skill_trees ---

    def create_skill_tree(self, *, game_id: int, name_en: str, name_ja: str | None = None,
                          category_tag: str | None = None, **extra) -> dict[str, Any]:
        return self._create(t.skill_trees, dict(game_id=game_id, name_en=name_en,
                                                name_ja=name_ja, category_tag=category_tag,
                                                **extra))

    def get_skill_tree(self, tree_id: int) -> dict[str, Any] | None:
        return self._get(t.skill_trees, id=tree_id)

    def list_skill_trees(self, game_id: int | None = None) -> list[dict[str, Any]]:
        criteria = [t.skill_trees.c.game_id == game_id] if game_id is not None else []
        return self._list(t.skill_trees, *criteria, order_by=t.skill_trees.c.name_en)

    def update_skill_tree(self, tree_id: int, **values) -> bool:
        return self._update(t.skill_trees, {"id": tree_id}, values)

    def delete_skill_tree(self, tree_id: int) -> bool:
        return self._delete(t.skill_trees, id=tree_id)

    # --- skills (threshold rows) ---

    def create_skill(self, *, tree_id: int, name_en: str, points: int,
                     name_ja: str | None = None, is_negative: bool = False,
                     **extra) -> dict[str, Any]:
        return self._create(t.skills, dict(tree_id=tree_id, name_en=name_en, points=points,
                                           name_ja=name_ja, is_negative=is_negative, **extra))

    def get_skill(self, skill_id: int) -> dict[str, Any] | None:
        return self._get(t.skills, id=skill_id)

    def list_skills_for_tree(self, tree_id: int) -> list[dict[str, Any]]:
        return self._list(t.skills, t.skills.c.tree_id == tree_id,
                          order_by=t.skills.c.points)

    def update_skill(self, skill_id: int, **values) -> bool:
        return self._update(t.skills, {"id": skill_id}, values)

    def delete_skill(self, skill_id: int) -> bool:
        return self._delete(t.skills, id=skill_id)

    # --- armor_pieces ---

    def create_armor_piece(self, *, game_id: int, slot: int, name_en: str, rarity: int,
                           slots: int, gender: int, hunter_type: int, defense: int,
                           max_defense: int, res_fire: int, res_water: int, res_ice: int,
                           res_thunder: int, res_dragon: int, name_ja: str | None = None,
                           hr_required: int = 0, village_stars: int = 0,
                           torso_inc: bool = False, is_event: bool = False,
                           **extra) -> dict[str, Any]:
        return self._create(t.armor_pieces, dict(
            game_id=game_id, slot=slot, name_en=name_en, name_ja=name_ja, rarity=rarity,
            slots=slots, gender=gender, hunter_type=hunter_type, hr_required=hr_required,
            village_stars=village_stars, defense=defense, max_defense=max_defense,
            res_fire=res_fire, res_water=res_water, res_ice=res_ice,
            res_thunder=res_thunder, res_dragon=res_dragon, torso_inc=torso_inc,
            is_event=is_event, **extra))

    def get_armor_piece(self, piece_id: int) -> dict[str, Any] | None:
        return self._get(t.armor_pieces, id=piece_id)

    def list_armor_pieces(
        self,
        game_id: int,
        *,
        slot: int | None = None,
        hunter_type: int | None = None,
        gender: int | None = None,
        max_hr: int | None = None,
        max_village_stars: int | None = None,
        allow_event: bool = False,
    ) -> list[dict[str, Any]]:
        c = t.armor_pieces.c
        criteria = [c.game_id == game_id]
        if slot is not None:
            criteria.append(c.slot == slot)
        if hunter_type is not None:
            criteria.append(c.hunter_type.in_([hunter_type, 2]))  # 2 = both
        if gender is not None:
            criteria.append(c.gender.in_([gender, 2]))
        # OR-availability (legacy Armor.cpp:102): a piece is excluded only when
        # it exceeds BOTH progression caps; a None cap leaves that path open.
        if max_hr is not None and max_village_stars is not None:
            criteria.append((c.hr_required <= max_hr) | (c.village_stars <= max_village_stars))
        elif max_hr is not None:
            criteria.append(c.hr_required <= max_hr)
        elif max_village_stars is not None:
            criteria.append(c.village_stars <= max_village_stars)
        if not allow_event:
            criteria.append(c.is_event.is_(False))
        return self._list(t.armor_pieces, *criteria, order_by=c.id)

    def update_armor_piece(self, piece_id: int, **values) -> bool:
        return self._update(t.armor_pieces, {"id": piece_id}, values)

    def delete_armor_piece(self, piece_id: int) -> bool:
        return self._delete(t.armor_pieces, id=piece_id)

    # --- armor_skills ---

    def set_armor_skill(self, *, armor_id: int, tree_id: int,
                        points: int) -> dict[str, Any]:
        return self._create(t.armor_skills, {"armor_id": armor_id, "tree_id": tree_id,
                                             "points": points})

    def get_armor_skill(self, armor_id: int, tree_id: int) -> dict[str, Any] | None:
        return self._get(t.armor_skills, armor_id=armor_id, tree_id=tree_id)

    def list_armor_skills_for_piece(self, armor_id: int) -> list[dict[str, Any]]:
        return self._list(t.armor_skills, t.armor_skills.c.armor_id == armor_id)

    def list_pieces_granting_tree(self, tree_id: int) -> list[dict[str, Any]]:
        return self._list(t.armor_skills, t.armor_skills.c.tree_id == tree_id)

    def update_armor_skill(self, armor_id: int, tree_id: int, **values) -> bool:
        return self._update(t.armor_skills, {"armor_id": armor_id, "tree_id": tree_id}, values)

    def delete_armor_skill(self, armor_id: int, tree_id: int) -> bool:
        return self._delete(t.armor_skills, armor_id=armor_id, tree_id=tree_id)

    # --- decorations ---

    def create_decoration(self, *, game_id: int, name_en: str, rarity: int, size: int,
                          name_ja: str | None = None, hr_required: int = 0,
                          village_stars: int = 0, is_event: bool = False,
                          **extra) -> dict[str, Any]:
        return self._create(t.decorations, dict(game_id=game_id, name_en=name_en,
                                                name_ja=name_ja, rarity=rarity, size=size,
                                                hr_required=hr_required,
                                                village_stars=village_stars,
                                                is_event=is_event, **extra))

    def get_decoration(self, decoration_id: int) -> dict[str, Any] | None:
        return self._get(t.decorations, id=decoration_id)

    def list_decorations(
        self,
        game_id: int,
        *,
        size: int | None = None,
        max_hr: int | None = None,
        max_village_stars: int | None = None,
        allow_event: bool = False,
    ) -> list[dict[str, Any]]:
        c = t.decorations.c
        criteria = [c.game_id == game_id]
        if size is not None:
            criteria.append(c.size == size)
        # OR-availability, same semantics as list_armor_pieces.
        if max_hr is not None and max_village_stars is not None:
            criteria.append((c.hr_required <= max_hr) | (c.village_stars <= max_village_stars))
        elif max_hr is not None:
            criteria.append(c.hr_required <= max_hr)
        elif max_village_stars is not None:
            criteria.append(c.village_stars <= max_village_stars)
        if not allow_event:
            criteria.append(c.is_event.is_(False))
        return self._list(t.decorations, *criteria, order_by=c.id)

    def update_decoration(self, decoration_id: int, **values) -> bool:
        return self._update(t.decorations, {"id": decoration_id}, values)

    def delete_decoration(self, decoration_id: int) -> bool:
        return self._delete(t.decorations, id=decoration_id)

    # --- decoration_skills ---

    def set_decoration_skill(self, *, decoration_id: int, tree_id: int,
                             points: int) -> dict[str, Any]:
        return self._create(t.decoration_skills, {"decoration_id": decoration_id,
                                                  "tree_id": tree_id, "points": points})

    def get_decoration_skill(self, decoration_id: int, tree_id: int) -> dict[str, Any] | None:
        return self._get(t.decoration_skills, decoration_id=decoration_id, tree_id=tree_id)

    def list_decoration_skills_for_decoration(self, decoration_id: int) -> list[dict[str, Any]]:
        return self._list(t.decoration_skills,
                          t.decoration_skills.c.decoration_id == decoration_id)

    def list_decorations_granting_tree(self, tree_id: int) -> list[dict[str, Any]]:
        return self._list(t.decoration_skills, t.decoration_skills.c.tree_id == tree_id)

    def update_decoration_skill(self, decoration_id: int, tree_id: int, **values) -> bool:
        return self._update(t.decoration_skills,
                            {"decoration_id": decoration_id, "tree_id": tree_id}, values)

    def delete_decoration_skill(self, decoration_id: int, tree_id: int) -> bool:
        return self._delete(t.decoration_skills, decoration_id=decoration_id, tree_id=tree_id)

    # --- charm_types ---

    def create_charm_type(self, *, game_id: int, code: str,
                          max_slots: int, **extra) -> dict[str, Any]:
        return self._create(t.charm_types, dict(game_id=game_id, code=code,
                                                max_slots=max_slots, **extra))

    def get_charm_type(self, charm_type_id: int) -> dict[str, Any] | None:
        return self._get(t.charm_types, id=charm_type_id)

    def list_charm_types(self, game_id: int) -> list[dict[str, Any]]:
        return self._list(t.charm_types, t.charm_types.c.game_id == game_id)

    def update_charm_type(self, charm_type_id: int, **values) -> bool:
        return self._update(t.charm_types, {"id": charm_type_id}, values)

    def delete_charm_type(self, charm_type_id: int) -> bool:
        return self._delete(t.charm_types, id=charm_type_id)

    # --- charm_skill_ranges ---

    def set_charm_skill_range(self, *, charm_type_id: int, tree_id: int, skill_slot: int,
                              min_points: int, max_points: int) -> dict[str, Any]:
        return self._create(t.charm_skill_ranges, {
            "charm_type_id": charm_type_id, "tree_id": tree_id, "skill_slot": skill_slot,
            "min_points": min_points, "max_points": max_points})

    def get_charm_skill_range(self, charm_type_id: int, tree_id: int,
                              skill_slot: int) -> dict[str, Any] | None:
        return self._get(t.charm_skill_ranges, charm_type_id=charm_type_id,
                         tree_id=tree_id, skill_slot=skill_slot)

    def list_charm_skill_ranges(self, charm_type_id: int) -> list[dict[str, Any]]:
        return self._list(t.charm_skill_ranges,
                          t.charm_skill_ranges.c.charm_type_id == charm_type_id)

    def update_charm_skill_range(self, charm_type_id: int, tree_id: int, skill_slot: int,
                                 **values) -> bool:
        return self._update(t.charm_skill_ranges,
                            {"charm_type_id": charm_type_id, "tree_id": tree_id,
                             "skill_slot": skill_slot}, values)

    def delete_charm_skill_range(self, charm_type_id: int, tree_id: int,
                                 skill_slot: int) -> bool:
        return self._delete(t.charm_skill_ranges, charm_type_id=charm_type_id,
                            tree_id=tree_id, skill_slot=skill_slot)

    # --- charm_slot_thresholds ---

    def set_charm_slot_threshold(self, *, charm_type_id: int, fulfillment: int,
                                 slots: int) -> dict[str, Any]:
        return self._create(t.charm_slot_thresholds, {"charm_type_id": charm_type_id,
                                                      "fulfillment": fulfillment,
                                                      "slots": slots})

    def get_charm_slot_threshold(self, charm_type_id: int,
                                 fulfillment: int) -> dict[str, Any] | None:
        return self._get(t.charm_slot_thresholds, charm_type_id=charm_type_id,
                         fulfillment=fulfillment)

    def list_charm_slot_thresholds(self, charm_type_id: int) -> list[dict[str, Any]]:
        return self._list(t.charm_slot_thresholds,
                          t.charm_slot_thresholds.c.charm_type_id == charm_type_id,
                          order_by=t.charm_slot_thresholds.c.fulfillment)

    def update_charm_slot_threshold(self, charm_type_id: int, fulfillment: int,
                                    **values) -> bool:
        return self._update(t.charm_slot_thresholds,
                            {"charm_type_id": charm_type_id, "fulfillment": fulfillment},
                            values)

    def delete_charm_slot_threshold(self, charm_type_id: int, fulfillment: int) -> bool:
        return self._delete(t.charm_slot_thresholds, charm_type_id=charm_type_id,
                            fulfillment=fulfillment)

    # --- mh3u_charm_tables ---

    def create_mh3u_charm_table_entry(self, *, game_id: int, table_index: int, tree_id: int,
                                      skill_slot: int, max_points: int,
                                      **extra) -> dict[str, Any]:
        return self._create(t.mh3u_charm_tables, dict(
            game_id=game_id, table_index=table_index, tree_id=tree_id,
            skill_slot=skill_slot, max_points=max_points, **extra))

    def get_mh3u_charm_table_entry(self, entry_id: int) -> dict[str, Any] | None:
        return self._get(t.mh3u_charm_tables, id=entry_id)

    def list_mh3u_charm_table(self, game_id: int,
                              table_index: int | None = None) -> list[dict[str, Any]]:
        c = t.mh3u_charm_tables.c
        criteria = [c.game_id == game_id]
        if table_index is not None:
            criteria.append(c.table_index == table_index)
        return self._list(t.mh3u_charm_tables, *criteria)

    def update_mh3u_charm_table_entry(self, entry_id: int, **values) -> bool:
        return self._update(t.mh3u_charm_tables, {"id": entry_id}, values)

    def delete_mh3u_charm_table_entry(self, entry_id: int) -> bool:
        return self._delete(t.mh3u_charm_tables, id=entry_id)
