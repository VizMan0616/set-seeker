"""SearchService: iterate-and-exclude orchestration (phase0-contracts.md §4).

Each page is at most PAGE_SIZE budgeted solves; every exclusion is persisted
in ``search_states`` via the user-data repository so "load more" is a
stateless re-solve (ADR 0005). Infeasible is a result, never an exception.
"""

import json
from collections.abc import Callable
from dataclasses import replace

from app.domain.models import (
    NONE_CHARM_ID,
    PAGE_SIZE,
    ArmorSetResult,
    CharmSpec,
    Query,
    SearchPage,
    SkillRequest,
    charm_mode_uses_generated,
    resolved_charm_mode,
)

# Tail census after the first page so the UI can say "N more to load".
# Only representative ids are walked; cards stay page-sized (ADR 0005).
_CENSUS_CAP = 500
from app.engine.data import PackData
from app.engine.pruning import PrunedPack, domain_snapshot, prune
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
            "excluded_charm_ids": list(query.excluded_charm_ids),
            "forced_piece_ids": list(query.forced_piece_ids),
            "forced_decoration_ids": list(query.forced_decoration_ids),
            "forced_charm_ids": list(query.forced_charm_ids),
            "sort": query.sort,
            "expand_equivalents": query.expand_equivalents,
            "use_generated_charms": query.use_generated_charms,
            "charm_mode": resolved_charm_mode(query),
            "user_charms": [
                {"id": c.id, "slots": c.slots, "skills": [list(p) for p in c.skills]}
                for c in query.user_charms
            ],
        }
    )


def _with_tally(
    query_json: str, *, delivered: int, found_total: int | None = None
) -> str:
    payload = json.loads(query_json)
    payload["delivered"] = delivered
    if found_total is not None:
        payload["found_total"] = found_total
    return json.dumps(payload)


def _found_total(query_json: str) -> int | None:
    value = json.loads(query_json).get("found_total")
    return int(value) if value is not None else None


def _delivered(query_json: str, fallback: int) -> int:
    value = json.loads(query_json).get("delivered")
    return int(value) if value is not None else fallback


def _page_units(query: Query, results: list[ArmorSetResult]) -> int:
    if query.expand_equivalents:
        return sum(r.equivalent_count() for r in results)
    return len(results)


def _query_from_json(payload: str) -> Query:
    d = json.loads(payload)
    raw_mode = d.get("charm_mode") or ""
    if raw_mode not in ("none", "inventory", "slotted", "one_skill", "two_skill"):
        raw_mode = "one_skill" if d.get("use_generated_charms", True) else "inventory"
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
        excluded_charm_ids=tuple(d.get("excluded_charm_ids") or ()),
        forced_piece_ids=tuple(d.get("forced_piece_ids") or ()),
        forced_decoration_ids=tuple(d.get("forced_decoration_ids") or ()),
        forced_charm_ids=tuple(d.get("forced_charm_ids") or ()),
        sort=d["sort"],
        expand_equivalents=bool(d.get("expand_equivalents", False)),
        use_generated_charms=charm_mode_uses_generated(raw_mode),
        charm_mode=raw_mode,
        user_charms=tuple(
            CharmSpec(
                id=c["id"],
                slots=c["slots"],
                skills=tuple((int(a), int(b)) for a, b in c["skills"]),
            )
            for c in d.get("user_charms") or ()
        ),
    )


def query_from_json(payload: str) -> Query:
    """Public loader for search_states.query_json (ignores snapshot extras)."""
    return _query_from_json(payload)


def _charm_skills_from_row(row: dict) -> tuple[tuple[int, int], ...]:
    skills = []
    if row.get("skill1_tree") is not None and row.get("skill1_points") is not None:
        skills.append((int(row["skill1_tree"]), int(row["skill1_points"])))
    if row.get("skill2_tree") is not None and row.get("skill2_points") is not None:
        skills.append((int(row["skill2_tree"]), int(row["skill2_points"])))
    return tuple(skills)


def _exclusion_tuple(result: ArmorSetResult) -> list[int]:
    charm = NONE_CHARM_ID if result.charm_id is None else result.charm_id
    return [*result.piece_ids, charm]


def _with_domain_snapshot(query_json: str, snapshot: dict) -> str:
    payload = json.loads(query_json)
    payload["domain_snapshot"] = snapshot
    return json.dumps(payload)


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
        pack = self._pack_loader(query.game)
        query = self._with_inventory(session_id, pack, query)
        pruned = prune(pack, query)
        state = self._user_data.create_search_state(
            session_id=session_id,
            game_id=pack.game_id,
            query_json=_with_domain_snapshot(
                _query_to_json(query), domain_snapshot(pack, pruned)
            ),
        )
        results, new_exclusions, partial, exhausted = self._solve_page(query, [])
        if new_exclusions:
            self._user_data.append_exclusions(state["id"], new_exclusions)
        shown = _page_units(query, results)
        remaining: int | None
        tally = state["query_json"]
        if exhausted:
            remaining = 0
            tally = _with_tally(tally, delivered=shown, found_total=shown)
        elif not results:
            remaining = None
            tally = _with_tally(tally, delivered=shown)
        else:
            extra, exact = self._count_further(
                query, [tuple(e) for e in new_exclusions]
            )
            if exact:
                remaining = extra
                tally = _with_tally(
                    tally, delivered=shown, found_total=shown + extra
                )
            else:
                remaining = None
                tally = _with_tally(tally, delivered=shown)
        if tally != state["query_json"]:
            self._user_data.update_search_query_json(state["id"], tally)
        return SearchPage(
            search_id=state["id"],
            results=tuple(results),
            partial=partial,
            exhausted=exhausted,
            shown_count=shown,
            remaining_count=remaining,
        )

    def get_search_query(self, session_id: str, search_id: str) -> Query | None:
        state = self._user_data.get_search_state(search_id)
        if state is None or state["session_id"] != session_id:
            return None
        return _query_from_json(state["query_json"])

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
        shown = _delivered(state["query_json"], len(exclusions)) + _page_units(
            query, results
        )
        total = _found_total(state["query_json"])
        remaining = 0 if exhausted else (None if total is None else max(total - shown, 0))
        self._user_data.update_search_query_json(
            search_id,
            _with_tally(
                state["query_json"],
                delivered=shown,
                found_total=total if total is not None else None,
            ),
        )
        return SearchPage(
            search_id=search_id,
            results=tuple(results),
            partial=partial,
            exhausted=exhausted,
            shown_count=shown,
            remaining_count=remaining,
        )

    def _with_inventory(self, session_id: str, pack: PackData, query: Query) -> Query:
        mode = resolved_charm_mode(query)
        synced = replace(
            query,
            charm_mode=mode,
            use_generated_charms=charm_mode_uses_generated(mode),
        )
        if not pack.talismans or mode == "none":
            return replace(synced, user_charms=())
        if synced.user_charms:
            return synced
        if mode != "inventory" and not charm_mode_uses_generated(mode):
            return synced
        rows = self._user_data.list_charms(session_id, pack.game_id)
        return replace(
            synced,
            user_charms=tuple(
                CharmSpec(
                    id=row["id"],
                    slots=row["slots"],
                    skills=_charm_skills_from_row(row),
                )
                for row in rows
            ),
        )

    def _solve_page(
        self, query: Query, exclusions: list[tuple[int, ...]]
    ) -> tuple[list[ArmorSetResult], list[list[int]], bool, bool]:
        mode = resolved_charm_mode(query)
        if (
            charm_mode_uses_generated(mode)
            and query.user_charms
            and not query.forced_charm_ids
        ):
            inv = replace(
                query,
                charm_mode="inventory",
                use_generated_charms=False,
            )
            inv_results, inv_excl, inv_partial, _inv_exh = self._solve_page(
                inv, exclusions
            )
            if inv_results:
                return inv_results, inv_excl, inv_partial, False

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
            exclusion = _exclusion_tuple(outcome.result)
            new_exclusions.append(exclusion)
            working.append(tuple(exclusion))
            if outcome.status == "feasible":
                # Budget hit mid-solve: the set is valid but ranking is not
                # proven; stop the page here and flag it.
                partial = True
                break

        return results, new_exclusions, partial, exhausted

    def _count_further(
        self, query: Query, exclusions: list[tuple[int, ...]]
    ) -> tuple[int, bool]:
        """How many more result units exist after ``exclusions``.

        One unit per representative, or per equivalent combination when
        ``query.expand_equivalents``. Walks iterate-and-exclude without
        keeping cards. ``exact`` is False when the budget or
        ``_CENSUS_CAP`` stops the walk.
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
            working.append(tuple(_exclusion_tuple(outcome.result)))
            extra += (
                outcome.result.equivalent_count()
                if query.expand_equivalents
                else 1
            )
            if outcome.status == "feasible":
                return extra, False
        return extra, False
