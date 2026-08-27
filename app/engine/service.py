"""SearchService: iterate-and-exclude orchestration (phase0-contracts.md §4).

Each page is at most PAGE_SIZE budgeted solves; every exclusion is persisted
in ``search_states`` via the user-data repository so "load more" is a
stateless re-solve (ADR 0005). Infeasible is a result, never an exception.
"""

import json
from collections.abc import Callable

from app.domain.models import PAGE_SIZE, ArmorSetResult, Query, SearchPage, SkillRequest

# Tail census after the first page so the UI can say "N more to load".
# Only representative ids are walked; cards stay page-sized (ADR 0005).
_CENSUS_CAP = 500
from app.engine.data import PackData
from app.engine.pruning import PrunedPack, prune
from app.engine.solver import solve_one
from app.repository.user_data import UserDataRepository


def _query_to_json(query: Query) -> str:
    return json.dumps(
        {
            "game": query.game,
            "skills": [[s.tree_id, s.min_points] for s in query.skills],
            "weapon_slots": query.weapon_slots,
            "gender": query.gender,
            "hunter_type": query.hunter_type,
            "hr": query.hr,
            "village_stars": query.village_stars,
            "allow_event": query.allow_event,
            "allow_bad_skills": query.allow_bad_skills,
            "allow_torso_inc": query.allow_torso_inc,
            "allow_dummy": query.allow_dummy,
            "excluded_piece_ids": list(query.excluded_piece_ids),
            "excluded_decoration_ids": list(query.excluded_decoration_ids),
            "sort": query.sort,
        }
    )


def _with_found_total(query_json: str, found_total: int) -> str:
    payload = json.loads(query_json)
    payload["found_total"] = found_total
    return json.dumps(payload)


def _found_total(query_json: str) -> int | None:
    value = json.loads(query_json).get("found_total")
    return int(value) if value is not None else None


def _query_from_json(payload: str) -> Query:
    d = json.loads(payload)
    return Query(
        game=d["game"],
        skills=tuple(SkillRequest(tree_id=t, min_points=p) for t, p in d["skills"]),
        weapon_slots=d["weapon_slots"],
        gender=d["gender"],
        hunter_type=d["hunter_type"],
        hr=d["hr"],
        village_stars=d["village_stars"],
        allow_event=d["allow_event"],
        allow_bad_skills=d["allow_bad_skills"],
        allow_torso_inc=d.get("allow_torso_inc", True),
        allow_dummy=d.get("allow_dummy", False),
        excluded_piece_ids=tuple(d.get("excluded_piece_ids") or ()),
        excluded_decoration_ids=tuple(d.get("excluded_decoration_ids") or ()),
        sort=d["sort"],
    )


class CpSatSearchService:
    """Concrete SearchService (phase0-contracts.md §4 protocol)."""

    def __init__(
        self,
        user_data: UserDataRepository,
        pack_loader: Callable[[str], PackData],
        *,
        time_limit_ms: int = 2000,
        page_size: int = PAGE_SIZE,
        num_workers: int = 8,
    ) -> None:
        # time_limit_ms / num_workers are passed in by the web layer from
        # app.config; the engine does not import config. Single-threaded
        # CP-SAT spends whole budgets *proving* optimality/infeasibility on
        # real packs; a parallel portfolio turns pages into sub-second solves.
        self._user_data = user_data
        self._pack_loader = pack_loader
        self._time_limit_ms = time_limit_ms
        self._page_size = page_size
        self._num_workers = num_workers

    def start_search(self, session_id: str, query: Query) -> SearchPage:
        self._user_data.get_or_create_session(session_id)
        # A new search from the same session invalidates its prior states.
        self._user_data.delete_search_states_for_session(session_id)
        state = self._user_data.create_search_state(
            session_id=session_id,
            game_id=self._pack_loader(query.game).game_id,
            query_json=_query_to_json(query),
        )
        results, new_exclusions, partial, exhausted = self._solve_page(query, [])
        if new_exclusions:
            self._user_data.append_exclusions(state["id"], new_exclusions)
        shown = len(results)
        remaining: int | None
        if exhausted:
            remaining = 0
            self._user_data.update_search_query_json(
                state["id"], _with_found_total(state["query_json"], shown)
            )
        elif not results:
            remaining = None
        else:
            extra, exact = self._count_further(
                query, [tuple(e) for e in new_exclusions]
            )
            if exact:
                remaining = extra
                self._user_data.update_search_query_json(
                    state["id"], _with_found_total(state["query_json"], shown + extra)
                )
            else:
                remaining = None
        return SearchPage(
            search_id=state["id"],
            results=tuple(results),
            partial=partial,
            exhausted=exhausted,
            shown_count=shown,
            remaining_count=remaining,
        )

    def load_more(self, session_id: str, search_id: str) -> SearchPage:
        state = self._user_data.get_search_state(search_id)
        if state is None or state["session_id"] != session_id:
            # Unknown or foreign search id (e.g. invalidated by a newer search):
            # an empty exhausted page, never an exception.
            return SearchPage(
                search_id=search_id, results=(), partial=False, exhausted=True,
                shown_count=0, remaining_count=0,
            )
        query = _query_from_json(state["query_json"])
        exclusions = [tuple(e) for e in json.loads(state["exclusions"])]
        results, new_exclusions, partial, exhausted = self._solve_page(query, exclusions)
        if new_exclusions:
            self._user_data.append_exclusions(search_id, new_exclusions)
        shown = len(exclusions) + len(results)
        total = _found_total(state["query_json"])
        remaining = 0 if exhausted else (None if total is None else max(total - shown, 0))
        return SearchPage(
            search_id=search_id,
            results=tuple(results),
            partial=partial,
            exhausted=exhausted,
            shown_count=shown,
            remaining_count=remaining,
        )

    def _solve_page(
        self, query: Query, exclusions: list[tuple[int, int, int, int, int]]
    ) -> tuple[list[ArmorSetResult], list[list[int]], bool, bool]:
        pack = self._pack_loader(query.game)
        pruned: PrunedPack = prune(pack, query)  # cached per (pack, query)

        results: list[ArmorSetResult] = []
        new_exclusions: list[list[int]] = []
        partial = False
        exhausted = False
        working = list(exclusions)

        for _ in range(self._page_size):
            outcome = solve_one(
                pack=pack,
                pruned=pruned,
                query=query,
                exclusions=working,
                time_limit_ms=self._time_limit_ms,
                num_workers=self._num_workers,
            )
            if outcome.status == "infeasible":
                exhausted = True
                break
            if outcome.result is None:  # budget hit before any solution
                partial = True
                break
            results.append(outcome.result)
            exclusion = list(outcome.result.piece_ids)
            new_exclusions.append(exclusion)
            working.append(tuple(exclusion))
            if outcome.status == "feasible":
                # Budget hit mid-solve: the set is valid but ranking is not
                # proven; stop the page here and flag it.
                partial = True
                break

        return results, new_exclusions, partial, exhausted

    def _count_further(
        self, query: Query, exclusions: list[tuple[int, int, int, int, int]]
    ) -> tuple[int, bool]:
        """How many more representative sets exist after ``exclusions``.

        Walks iterate-and-exclude without keeping cards. ``exact`` is False
        when the budget or ``_CENSUS_CAP`` stops the walk.
        """
        pack = self._pack_loader(query.game)
        pruned: PrunedPack = prune(pack, query)
        working = list(exclusions)
        extra = 0
        for _ in range(_CENSUS_CAP):
            outcome = solve_one(
                pack=pack,
                pruned=pruned,
                query=query,
                exclusions=working,
                time_limit_ms=self._time_limit_ms,
                num_workers=self._num_workers,
            )
            if outcome.status == "infeasible":
                return extra, True
            if outcome.result is None:
                return extra, False
            working.append(tuple(outcome.result.piece_ids))
            extra += 1
            if outcome.status == "feasible":
                return extra, False
        return extra, False
