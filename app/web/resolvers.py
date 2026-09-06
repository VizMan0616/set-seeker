"""Repository-backed NameResolver + Catalog (phase0-contracts §5).

Real implementations of the protocols in ``app.web.present``, replacing the
fixture-backed mock at integration. Reads go through ``GameDataRepository``
only (ADR 0004); hot lookups are memoized because result rendering resolves
the same ids repeatedly.
"""

import json
from typing import Any

from app.repository.game_data import GameDataRepository

DEFAULT_DESIRED_SKILLS_MAX = 5
DEFAULT_CHARM_POINTS = {
    "skill1_min": 1,
    "skill1_max": 10,
    "skill2_min": -10,
    "skill2_max": 13,
}


def _features(features_json: str | None) -> dict:
    return json.loads(features_json or "{}")


def progression_caps(features_json: str | None) -> dict[str, int]:
    """Guild HR and village ★ ceilings from games.features (pack manifest)."""
    data = _features(features_json)
    return {
        "guild_rank": int(data.get("guild_rank_max") or 9),
        "village_stars": int(data.get("village_stars_max") or 9),
    }


def desired_skills_max(features_json: str | None) -> int:
    """Athena Form1.h NumSkills, stored on games.features from the pack manifest."""
    value = _features(features_json).get("desired_skills_max")
    try:
        n = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DESIRED_SKILLS_MAX
    return n if n >= 1 else DEFAULT_DESIRED_SKILLS_MAX


def torso_inc_display_name(
    repo: GameDataRepository,
    game_id: int,
    features_json: str | None,
) -> str | None:
    """Pack's Torso Inc / Torso Up label, or None if the mechanic is absent.

    Prefers ``games.features.torso_inc_name`` (ETL, from the empty-threshold
    tree). Falls back to pieces-with-flag + a threshold-less skill tree so
    fixture packs and a stale DB still agree with game data.
    """
    stored = _features(features_json).get("torso_inc_name")
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    if not repo.has_torso_inc_pieces(game_id):
        return None
    for tree in repo.list_skill_trees(game_id):
        if not repo.list_skills_for_tree(tree["id"]):
            return tree["name_en"]
    return None


def charm_point_bounds(features_json: str | None) -> dict[str, int]:
    """Per-slot inventory stepper ranges (skill 1 ≠ skill 2)."""
    data = _features(features_json).get("charm_points") or {}
    out = dict(DEFAULT_CHARM_POINTS)
    for key in DEFAULT_CHARM_POINTS:
        try:
            out[key] = int(data[key])
        except (KeyError, TypeError, ValueError):
            pass
    return out


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
                "has_dummy": False,
                "torso_inc_name": None,
                "progression": {"guild_rank": 9, "village_stars": 9},
                "desired_skills_max": DEFAULT_DESIRED_SKILLS_MAX,
            }
        game_id = row["id"]
        return {
            "categories": [c["tag"] for c in self._repo.list_skill_categories(game_id)],
            "talismans": bool(json.loads(row["features"] or "{}").get("talismans", False)),
            "has_dummy": self._repo.has_dummy_pieces(game_id),
            "torso_inc_name": torso_inc_display_name(
                self._repo,
                game_id,
                row["features"],
            ),
            "progression": progression_caps(row["features"]),
            "desired_skills_max": desired_skills_max(row["features"]),
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
