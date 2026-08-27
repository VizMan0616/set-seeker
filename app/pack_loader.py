"""Build the engine's in-memory PackData from the database (integration seam).

The engine is pure and may not import the repository layer
(phase0-contracts.md §3, §7), so this module — outside ``app.engine`` — reads
a loaded pack via ``GameDataRepository`` and constructs the
``app.engine.data.PackData`` the solver consumes. Loaded packs are cached;
the web layer loads every pack once at startup.
"""

import json

from app.engine.data import ArmorPiece, Decoration, PackData, SkillThreshold
from app.repository.game_data import GameDataRepository


class PackNotLoadedError(RuntimeError):
    """The requested game pack has not been ETL'd into the database."""


class PackLoader:
    """Callable pack cache: ``pack_loader("mhfu")`` -> ``PackData``."""

    def __init__(self, repo: GameDataRepository) -> None:
        self._repo = repo
        self._cache: dict[str, PackData] = {}

    def __call__(self, game: str) -> PackData:
        if game not in self._cache:
            self._cache[game] = self._load(game)
        return self._cache[game]

    def _load(self, game: str) -> PackData:
        row = self._repo.get_game_by_code(game)
        if row is None:
            raise PackNotLoadedError(
                f"game pack {game!r} is not in the database — "
                f"run `python -m app.etl --pack {game}` first"
            )
        game_id = row["id"]

        pieces = tuple(
            ArmorPiece(
                id=p["id"],
                slot=p["slot"],
                slots=p["slots"],
                defense=p["defense"],
                rarity=p["rarity"],
                skills=tuple(
                    (s["tree_id"], s["points"])
                    for s in self._repo.list_armor_skills_for_piece(p["id"])
                ),
                torso_inc=bool(p["torso_inc"]),
                gender=p["gender"],
                hunter_type=p["hunter_type"],
                hr_required=p["hr_required"],
                village_stars=p["village_stars"],
                is_event=bool(p["is_event"]),
                is_dummy=bool(p.get("is_dummy", False)),
                res_fire=p["res_fire"],
                res_water=p["res_water"],
                res_ice=p["res_ice"],
                res_thunder=p["res_thunder"],
                res_dragon=p["res_dragon"],
            )
            for p in self._repo.list_armor_pieces(game_id, allow_event=True)
        )
        decorations = tuple(
            Decoration(
                id=d["id"],
                size=d["size"],
                skills=tuple(
                    (s["tree_id"], s["points"])
                    for s in self._repo.list_decoration_skills_for_decoration(d["id"])
                ),
                rarity=d["rarity"],
                hr_required=d["hr_required"],
                village_stars=d["village_stars"],
                is_event=bool(d["is_event"]),
            )
            for d in self._repo.list_decorations(game_id, allow_event=True)
        )
        skills = tuple(
            SkillThreshold(
                id=s["id"],
                tree_id=s["tree_id"],
                points=s["points"],
                is_negative=bool(s["is_negative"]),
            )
            for tree in self._repo.list_skill_trees(game_id)
            for s in self._repo.list_skills_for_tree(tree["id"])
        )
        features = json.loads(row["features"])
        return PackData(
            game=game,
            game_id=game_id,
            pieces=pieces,
            decorations=decorations,
            skills=skills,
            talismans=bool(features.get("talismans", False)),
        )
