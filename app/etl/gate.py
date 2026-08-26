"""Known-query validation gate (run-etl rule 4, phase0-contracts.md §9).

Property-based until real legacy reference sets are captured: exact spot checks
against the legacy source data, exact row counts, and data-feasibility checks
for classic queries. A failed gate means the build failed.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.repository.game_data import GameDataRepository

GENDER = {"m": 0, "male": 0, "f": 1, "female": 1, "both": 2}
HUNTER_TYPE = {"blademaster": 0, "gunner": 1, "both": 2}
SLOT = {"head": 0, "body": 1, "arms": 2, "waist": 3, "legs": 4}

# Conservative decoration budget for tree_coverage: five usable slots across the
# whole set at the best jewel for the tree.
DECO_SLOT_BUDGET = 5


@dataclass(frozen=True)
class GateResult:
    name: str
    ok: bool
    detail: str = ""


class Gate:
    def __init__(self, repo: GameDataRepository, game_id: int) -> None:
        self._repo = repo
        self._game_id = game_id
        self._tree_ids = {
            row["name_en"]: row["id"] for row in repo.list_skill_trees(game_id)
        }

    def run(self, suite: dict[str, Any]) -> list[GateResult]:
        results: list[GateResult] = []
        expected_counts = suite.get("row_counts")
        if expected_counts:
            results.append(self._check_row_counts(expected_counts))
        for query in suite.get("queries", []):
            handler = getattr(self, f"_check_{query['type']}", None)
            if handler is None:
                results.append(GateResult(query["name"], False,
                                          f"unknown query type {query['type']!r}"))
            else:
                results.append(handler(query))
        return results

    # --- check types ---

    def _check_row_counts(self, expected: dict[str, int]) -> GateResult:
        from app.etl.writer import table_counts

        actual = table_counts(self._repo, self._game_id)
        mismatches = {
            table: {"expected": want, "actual": actual.get(table)}
            for table, want in expected.items()
            if actual.get(table) != want
        }
        return GateResult("row_counts", not mismatches,
                          "" if not mismatches else f"mismatches: {mismatches}")

    def _check_skill_threshold(self, query: dict[str, Any]) -> GateResult:
        tree_id = self._tree_ids.get(query["tree"])
        if tree_id is None:
            return GateResult(query["name"], False, f"tree {query['tree']!r} not found")
        for skill in self._repo.list_skills_for_tree(tree_id):
            if skill["name_en"] == query["skill"]:
                expect = query["expect"]
                ok = (skill["points"] == expect["points"]
                      and bool(skill["is_negative"]) == expect["is_negative"])
                return GateResult(query["name"], ok,
                                  "" if ok else f"got {skill}")
        return GateResult(query["name"], False,
                          f"skill {query['skill']!r} not found under {query['tree']!r}")

    def _check_armor_piece(self, query: dict[str, Any]) -> GateResult:
        pieces = [p for p in self._repo.list_armor_pieces(
            self._game_id, slot=SLOT[query["slot"]], allow_event=True)
            if p["name_en"] == query["name_en"]]
        if not pieces:
            return GateResult(query["name"], False,
                              f"piece {query['name_en']!r} not found")
        piece = pieces[0]
        expect = query["expect"]
        problems = _diff_scalar_fields(piece, expect)
        if "skills" in expect:
            actual = {
                self._tree_name(row["tree_id"]): row["points"]
                for row in self._repo.list_armor_skills_for_piece(piece["id"])
            }
            if actual != expect["skills"]:
                problems.append(f"skills: expected {expect['skills']}, got {actual}")
        return GateResult(query["name"], not problems, "; ".join(problems))

    def _check_decoration(self, query: dict[str, Any]) -> GateResult:
        decos = [d for d in self._repo.list_decorations(self._game_id, allow_event=True)
                 if d["name_en"] == query["name_en"]]
        if not decos:
            return GateResult(query["name"], False,
                              f"decoration {query['name_en']!r} not found")
        deco = decos[0]
        expect = query["expect"]
        problems = _diff_scalar_fields(deco, expect)
        if "skills" in expect:
            actual = {
                self._tree_name(row["tree_id"]): row["points"]
                for row in self._repo.list_decoration_skills_for_decoration(deco["id"])
            }
            if actual != expect["skills"]:
                problems.append(f"skills: expected {expect['skills']}, got {actual}")
        return GateResult(query["name"], not problems, "; ".join(problems))

    def _check_tree_coverage(self, query: dict[str, Any]) -> GateResult:
        """Data feasibility: the pack must be able to activate each requested tree.

        Per tree, the best achievable points — sum of per-slot armor maximums
        plus DECO_SLOT_BUDGET sockets of the best jewel — must reach the
        threshold. This stands in for solver replay until the engine lands.
        """
        hunter_type = HUNTER_TYPE[query.get("hunter_type", "both")]
        gender = GENDER.get(query.get("gender", "both"), 2)
        pieces = self._repo.list_armor_pieces(
            self._game_id, hunter_type=hunter_type, gender=gender,
            max_hr=query.get("hr"), max_village_stars=query.get("village_stars"))
        piece_by_id = {p["id"]: p for p in pieces}
        decos = self._repo.list_decorations(
            self._game_id, max_hr=query.get("hr"),
            max_village_stars=query.get("village_stars"))
        deco_ids = {d["id"] for d in decos}

        problems = []
        for tree_name, threshold in query["trees"].items():
            tree_id = self._tree_ids.get(tree_name)
            if tree_id is None:
                problems.append(f"tree {tree_name!r} not found")
                continue
            per_slot_max = [0] * 5
            for grant in self._repo.list_pieces_granting_tree(tree_id):
                piece = piece_by_id.get(grant["armor_id"])
                if piece is not None and grant["points"] > 0:
                    slot = piece["slot"]
                    per_slot_max[slot] = max(per_slot_max[slot], grant["points"])
            best_deco = max(
                (g["points"] for g in self._repo.list_decorations_granting_tree(tree_id)
                 if g["decoration_id"] in deco_ids and g["points"] > 0),
                default=0,
            )
            achievable = sum(per_slot_max) + DECO_SLOT_BUDGET * best_deco
            if achievable < threshold:
                problems.append(
                    f"{tree_name}: needs {threshold}, data reaches {achievable} "
                    f"(per-slot max {per_slot_max}, best jewel {best_deco})")
        return GateResult(query["name"], not problems, "; ".join(problems))

    # --- helpers ---

    def _tree_name(self, tree_id: int) -> str:
        tree = self._repo.get_skill_tree(tree_id)
        return tree["name_en"] if tree else f"#{tree_id}"


def _diff_scalar_fields(row: dict[str, Any], expect: dict[str, Any]) -> list[str]:
    problems = []
    for key, want in expect.items():
        if key == "skills":
            continue
        if key == "gender":
            want = GENDER[want]
        elif key == "hunter_type":
            want = HUNTER_TYPE[want]
        got = row.get(key)
        if isinstance(want, bool):
            got = bool(got)
        if got != want:
            problems.append(f"{key}: expected {want!r}, got {got!r}")
    return problems


def run_gate(repo: GameDataRepository, game_id: int,
             pack_dir: Path) -> tuple[bool, list[GateResult]]:
    suite_path = pack_dir / "known_queries.yaml"
    suite = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    results = Gate(repo, game_id).run(suite)
    return all(r.ok for r in results), results
