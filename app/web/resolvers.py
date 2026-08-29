"""Repository-backed NameResolver + Catalog (phase0-contracts §5).

Real implementations of the protocols in ``app.web.present``, replacing the
fixture-backed mock at integration. Reads go through ``GameDataRepository``
only (ADR 0004); hot lookups are memoized because result rendering resolves
the same ids repeatedly.
"""

import json
from typing import Any

from app.repository.game_data import GameDataRepository


def progression_caps(features_json: str | None) -> dict[str, int]:
    """Guild HR and village ★ ceilings from games.features (pack manifest)."""
    data = json.loads(features_json or "{}")
    return {
        "guild_rank": int(data.get("guild_rank_max") or 9),
        "village_stars": int(data.get("village_stars_max") or 9),
    }


class RepositoryNameResolver:
    def __init__(self, repo: GameDataRepository) -> None:
        self._repo = repo
        self._pieces: dict[int, dict[str, Any]] = {}
        self._deco_names: dict[int, str] = {}
        self._skill_names: dict[int, str] = {}
        self._tree_names: dict[int, str] = {}

    def armor_piece(self, piece_id: int) -> dict[str, Any]:
        if piece_id not in self._pieces:
            row = self._repo.get_armor_piece(piece_id)
            if row is None:
                raise KeyError(f"unknown armor piece id {piece_id}")
            self._pieces[piece_id] = {
                "name": row["name_en"],
                "rarity": row["rarity"],
                "defense": row["defense"],
                "slots": row["slots"],
            }
        return self._pieces[piece_id]

    def decoration_name(self, decoration_id: int) -> str:
        if decoration_id not in self._deco_names:
            row = self._repo.get_decoration(decoration_id)
            if row is None:
                raise KeyError(f"unknown decoration id {decoration_id}")
            self._deco_names[decoration_id] = row["name_en"]
        return self._deco_names[decoration_id]

    def skill_name(self, skill_id: int) -> str:
        if skill_id not in self._skill_names:
            row = self._repo.get_skill(skill_id)
            if row is None:
                raise KeyError(f"unknown skill id {skill_id}")
            self._skill_names[skill_id] = row["name_en"]
        return self._skill_names[skill_id]

    def skill_tree_name(self, tree_id: int) -> str:
        if tree_id not in self._tree_names:
            row = self._repo.get_skill_tree(tree_id)
            if row is None:
                raise KeyError(f"unknown skill tree id {tree_id}")
            self._tree_names[tree_id] = row["name_en"]
        return self._tree_names[tree_id]


class RepositoryCatalog:
    """Form options for the index page (games + skill trees)."""

    def __init__(self, repo: GameDataRepository) -> None:
        self._repo = repo

    def list_games(self) -> list[dict[str, Any]]:
        return self._repo.list_games()

    def list_skill_trees(self, game: str) -> list[dict[str, Any]]:
        row = self._repo.get_game_by_code(game)
        if row is None:
            return []
        return [
            {
                "id": tree["id"],
                "name": tree["name_en"],
                "thresholds": [
                    {"skill_id": s["id"], "name": s["name_en"], "points": s["points"]}
                    for s in self._repo.list_skills_for_tree(tree["id"])
                    if not s["is_negative"]
                ],
            }
            for tree in self._repo.list_skill_trees(row["id"])
        ]

    def list_search_catalog(self, game: str) -> dict[str, Any]:
        """Skills and pack-scoped categories for the search form."""
        row = self._repo.get_game_by_code(game)
        if row is None:
            return {
                "categories": [],
                "skills": [],
                "talismans": False,
                "progression": {"guild_rank": 9, "village_stars": 9},
            }
        game_id = row["id"]
        return {
            "categories": [c["tag"] for c in self._repo.list_skill_categories(game_id)],
            "talismans": bool(json.loads(row["features"] or "{}").get("talismans", False)),
            "progression": progression_caps(row["features"]),
            "skills": [
                {
                    "id": s["id"],
                    "name": s["name_en"],
                    "tree_id": s["tree_id"],
                    "tree_name": s["tree_name"],
                    "points": s["points"],
                    "categories": s["categories"],
                }
                for s in self._repo.list_skills_for_game(game_id)
            ],
        }
