"""SearchService: iterate-and-exclude orchestration (phase0-contracts.md §4).

Each page is at most PAGE_SIZE budgeted solves; every exclusion is persisted
in ``search_states`` via the user-data repository so "load more" is a
stateless re-solve (ADR 0005). Infeasible is a result, never an exception.
At most one prefetched page sits in query_json (lookahead), never a 1000-set buffer.
"""

import json
import threading
import time
from collections.abc import Callable
from dataclasses import replace

from app.domain.models import (
    NONE_CHARM_ID,
    PAGE_SIZE,
    SHOWN_CAP,
    ArmorSetResult,
    CharmSpec,
    DecorationAssignment,
    Query,
    SearchPage,
    SkillRequest,
    charm_mode_uses_generated,
    resolved_charm_mode,
)

# Tail census after the first page so the UI can say "N more to load".
# Only representative ids are walked; cards stay page-sized (ADR 0005).
_CENSUS_CAP = 500
# Tail-count budget inside start_search so census cannot monopolize the global
# solve slot long enough to starve concurrent requests (503 SearchBusyError).
_CENSUS_BUDGET_S = 8.0
from app.engine.data import PackData
from app.engine.pruning import PrunedPack, domain_snapshot, prune
from app.engine.solver import solve_one
from app.repository.user_data import UserDataRepository


class SearchBusyError(Exception):
    """No global solve slot within the queue wait (other users still served)."""

    def __init__(
        self, message: str = "The search engine is busy. Try again in a moment."
    ) -> None:
        super().__init__(message)
        self.message = message


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


def _result_to_json(result: ArmorSetResult) -> dict:
    return {
        "piece_ids": list(result.piece_ids),
        "alternates": [list(a) for a in result.alternates],
        "decorations": [
            {"decoration_id": d.decoration_id, "count": d.count}
            for d in result.decorations
        ],
        "charm_id": result.charm_id,
        "active_skills": [list(p) for p in result.active_skills],
        "spare_slots": list(result.spare_slots),
        "defense": result.defense,
        "charm_slots": result.charm_slots,
        "charm_skills": [list(p) for p in result.charm_skills],
    }


def _result_from_json(d: dict) -> ArmorSetResult:
    return ArmorSetResult(
        piece_ids=tuple(d["piece_ids"]),
        alternates=tuple(tuple(a) for a in d["alternates"]),
        decorations=tuple(
            DecorationAssignment(
                decoration_id=x["decoration_id"], count=x["count"]
            )
            for x in d["decorations"]
        ),
        charm_id=d["charm_id"],
        active_skills=tuple((int(a), int(b)) for a, b in d["active_skills"]),
        spare_slots=tuple(d["spare_slots"]),
        defense=d["defense"],
        charm_slots=int(d.get("charm_slots") or 0),
        charm_skills=tuple(
            (int(a), int(b)) for a, b in d.get("charm_skills") or ()
        ),
    )


def _shown_capped(query_json: str) -> bool:
    return bool(json.loads(query_json).get("shown_capped"))


def _lookahead_payload(query_json: str) -> dict | None:
    raw = json.loads(query_json).get("lookahead")
    return raw if isinstance(raw, dict) else None


def _patch_query_json(query_json: str, **fields) -> str:
    payload = json.loads(query_json)
    for key, value in fields.items():
        if value is _UNSET:
            payload.pop(key, None)
        else:
            payload[key] = value
    return json.dumps(payload)


_UNSET = object()


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
        shown_cap: int = SHOWN_CAP,
        max_inflight: int = 1,
        queue_wait_s: float = 30.0,
    ) -> None:
        # time_limit_ms / num_workers are passed in by the web layer from
        # app.config; the engine does not import config. Single-threaded
        # CP-SAT spends whole budgets *proving* optimality/infeasibility on
        # real packs; a parallel portfolio turns pages into sub-second solves.
        # max_inflight is a *process-wide* solve-job cap (not OR-Tools workers).
        self._user_data = user_data
        self._pack_loader = pack_loader
        self._time_limit_ms = time_limit_ms
        self._page_size = page_size
        self._num_workers = num_workers
        self._shown_cap = shown_cap
        self._queue_wait_s = queue_wait_s
        self._slots = threading.BoundedSemaphore(max(1, max_inflight))
        self._lock = threading.Lock()
        self._session_epoch: dict[str, int] = {}
        self._prefetching: set[str] = set()

    def _acquire_interactive(self) -> None:
        if not self._slots.acquire(timeout=self._queue_wait_s):
            raise SearchBusyError()

    def _release_slot(self) -> None:
        self._slots.release()

    def start_search(self, session_id: str, query: Query) -> SearchPage:
        self._acquire_interactive()
        try:
            with self._lock:
                epoch = self._session_epoch.get(session_id, 0) + 1
                self._session_epoch[session_id] = epoch
                self._user_data.get_or_create_session(session_id)
                # A new search from the same session invalidates its prior states.
                self._user_data.delete_search_states_for_session(session_id)
                pack = self._pack_loader(query.game)
                query = self._with_inventory(session_id, pack, query)
                snap_query = (
                    replace(query, use_generated_charms=False)
                    if query.user_charms and query.use_generated_charms
                    else query
                )
                pruned = prune(pack, snap_query)
                state = self._user_data.create_search_state(
                    session_id=session_id,
                    game_id=pack.game_id,
                    query_json=_with_domain_snapshot(
                        _query_to_json(query), domain_snapshot(pack, pruned)
                    ),
                )
            results, new_exclusions, partial, exhausted = self._solve_page(
                query, [], shown_so_far=0
            )
            shown = _page_units(query, results)
            remaining: int | None
            tally = state["query_json"]
            capped = shown >= self._shown_cap
            if exhausted or capped:
                remaining = 0
                exhausted = True
                tally = _with_tally(tally, delivered=shown, found_total=shown)
                tally = _patch_query_json(tally, shown_capped=capped)
            elif not results:
                remaining = None
                tally = _with_tally(tally, delivered=shown)
            else:
                extra, exact = self._count_further(
                    snap_query,
                    [tuple(e) for e in new_exclusions],
                    deadline=time.monotonic() + _CENSUS_BUDGET_S,
                )
                if exact:
                    remaining = extra
                    tally = _with_tally(
                        tally, delivered=shown, found_total=shown + extra
                    )
                else:
                    remaining = None
                    tally = _with_tally(tally, delivered=shown)
            with self._lock:
                if self._session_epoch.get(session_id) == epoch:
                    if new_exclusions:
                        self._user_data.append_exclusions(state["id"], new_exclusions)
                    if tally != state["query_json"]:
                        self._user_data.update_search_query_json(state["id"], tally)
            page = SearchPage(
                search_id=state["id"],
                results=tuple(results),
                partial=partial,
                exhausted=exhausted,
                shown_count=shown,
                remaining_count=remaining,
            )
        finally:
            self._release_slot()
        if not page.exhausted:
            self._schedule_prefetch(session_id, page.search_id, epoch)
        return page

    def get_search_query(self, session_id: str, search_id: str) -> Query | None:
        state = self._user_data.get_search_state(search_id)
        if state is None or state["session_id"] != session_id:
            return None
        return _query_from_json(state["query_json"])

    def load_more(self, session_id: str, search_id: str) -> SearchPage:
        page = self._load_more_body(session_id, search_id)
        if not page.exhausted:
            self._schedule_prefetch(
                session_id, search_id, self._session_epoch.get(session_id, 0)
            )
        return page

    def _load_more_body(self, session_id: str, search_id: str) -> SearchPage:
        with self._lock:
            state = self._user_data.get_search_state(search_id)
            if state is None or state["session_id"] != session_id:
                return SearchPage(
                    search_id=search_id, results=(), partial=False, exhausted=True,
                    shown_count=0, remaining_count=0,
                )
            if _shown_capped(state["query_json"]):
                shown = _delivered(state["query_json"], 0)
                return SearchPage(
                    search_id=search_id,
                    results=(),
                    partial=False,
                    exhausted=True,
                    shown_count=shown,
                    remaining_count=0,
                )
            query = _query_from_json(state["query_json"])
            ahead = _lookahead_payload(state["query_json"])
            if ahead is not None:
                results = [_result_from_json(r) for r in ahead["results"]]
                partial = bool(ahead.get("partial"))
                exhausted = bool(ahead.get("exhausted"))
                return self._commit_load_more(
                    search_id, state, query, results, partial, exhausted
                )
            exclusions = [tuple(e) for e in json.loads(state["exclusions"])]
            shown_so_far = _delivered(state["query_json"], len(exclusions))
            excl_snap = state["exclusions"]

        self._acquire_interactive()
        try:
            results, new_exclusions, partial, exhausted = self._solve_page(
                query, exclusions, shown_so_far=shown_so_far
            )
        finally:
            self._release_slot()

        with self._lock:
            state = self._user_data.get_search_state(search_id)
            if state is None or state["session_id"] != session_id:
                return SearchPage(
                    search_id=search_id, results=(), partial=False, exhausted=True,
                    shown_count=0, remaining_count=0,
                )
            if (
                state["exclusions"] == excl_snap
                and not _lookahead_payload(state["query_json"])
            ):
                if new_exclusions:
                    self._user_data.append_exclusions(search_id, new_exclusions)
                return self._commit_load_more(
                    search_id, state, query, results, partial, exhausted
                )
        return self._load_more_body(session_id, search_id)

    def _commit_load_more(
        self,
        search_id: str,
        state: dict,
        query: Query,
        results: list[ArmorSetResult],
        partial: bool,
        exhausted: bool,
    ) -> SearchPage:
        shown = _delivered(state["query_json"], 0) + _page_units(query, results)
        total = _found_total(state["query_json"])
        capped = shown >= self._shown_cap
        if capped:
            exhausted = True
        remaining = 0 if exhausted else (
            None if total is None else max(total - shown, 0)
        )
        tally = _with_tally(
            state["query_json"],
            delivered=shown,
            found_total=shown if capped else (total if total is not None else None),
        )
        tally = _patch_query_json(
            tally,
            lookahead=_UNSET,
            shown_capped=capped,
        )
        self._user_data.update_search_query_json(search_id, tally)
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

    def _schedule_prefetch(
        self, session_id: str, search_id: str, epoch: int
    ) -> None:
        with self._lock:
            if search_id in self._prefetching:
                return
            self._prefetching.add(search_id)
        thread = threading.Thread(
            target=self._prefetch_one,
            args=(session_id, search_id, epoch),
            daemon=True,
            name=f"prefetch-{search_id[:8]}",
        )
        thread.start()

    def _prefetch_one(self, session_id: str, search_id: str, epoch: int) -> None:
        try:
            # Skip rather than queue: prefetch must not stack behind inflight solves.
            if not self._slots.acquire(blocking=False):
                return
            try:
                self._prefetch_solve(session_id, search_id, epoch)
            finally:
                self._slots.release()
        finally:
            with self._lock:
                self._prefetching.discard(search_id)

    def _prefetch_solve(self, session_id: str, search_id: str, epoch: int) -> None:
        with self._lock:
            if self._session_epoch.get(session_id) != epoch:
                return
            state = self._user_data.get_search_state(search_id)
            if state is None or state["session_id"] != session_id:
                return
            if _shown_capped(state["query_json"]) or _lookahead_payload(
                state["query_json"]
            ):
                return
            query = _query_from_json(state["query_json"])
            exclusions = [tuple(e) for e in json.loads(state["exclusions"])]
            shown_so_far = _delivered(state["query_json"], len(exclusions))
            if shown_so_far >= self._shown_cap:
                return
            excl_snap = state["exclusions"]
        results, new_exclusions, partial, exhausted = self._solve_page(
            query, exclusions, shown_so_far=shown_so_far
        )
        with self._lock:
            if self._session_epoch.get(session_id) != epoch:
                return
            state = self._user_data.get_search_state(search_id)
            if state is None or state["session_id"] != session_id:
                return
            if state["exclusions"] != excl_snap:
                return
            if _shown_capped(state["query_json"]) or _lookahead_payload(
                state["query_json"]
            ):
                return
            if new_exclusions:
                self._user_data.append_exclusions(search_id, new_exclusions)
            tally = _patch_query_json(
                state["query_json"],
                lookahead={
                    "results": [_result_to_json(r) for r in results],
                    "partial": partial,
                    "exhausted": exhausted,
                },
            )
            self._user_data.update_search_query_json(search_id, tally)

    def _solve_page(
        self,
        query: Query,
        exclusions: list[tuple[int, ...]],
        *,
        shown_so_far: int,
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
                inv, exclusions, shown_so_far=shown_so_far
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
            if shown_so_far + _page_units(query, results) >= self._shown_cap:
                exhausted = True
                break
            outcome = solve_one(
                pack=pack,
                pruned=pruned,
                query=query,
                exclusions=working,
                time_limit_ms=self._time_limit_ms,
                num_workers=self._num_workers,
            )
            if (
                outcome.result is None
                and outcome.status == "unknown"
                and query.use_generated_charms
                and not results
            ):
                outcome = solve_one(
                    pack=pack,
                    pruned=pruned,
                    query=query,
                    exclusions=working,
                    time_limit_ms=self._time_limit_ms,
                    num_workers=self._num_workers,
                    rank=False,
                )
            if outcome.status == "infeasible":
                exhausted = True
                break
            if outcome.result is None:  # budget hit before any solution
                partial = True
                break
            next_units = _page_units(query, [outcome.result])
            if (
                shown_so_far + _page_units(query, results) + next_units
                > self._shown_cap
                and results
            ):
                exhausted = True
                break
            results.append(outcome.result)
            exclusion = _exclusion_tuple(outcome.result)
            new_exclusions.append(exclusion)
            working.append(tuple(exclusion))
            if shown_so_far + _page_units(query, results) >= self._shown_cap:
                exhausted = True
                break
            if outcome.status == "unranked":
                # Feasibility-first: ranking incomplete; keep filling the page.
                partial = True
                continue
            if outcome.status == "feasible":
                # Budget hit mid-solve: the set is valid but ranking is not
                # proven; stop the page here and flag it.
                partial = True
                break

        return results, new_exclusions, partial, exhausted

    def _count_further(
        self,
        query: Query,
        exclusions: list[tuple[int, ...]],
        *,
        deadline: float | None = None,
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
            if deadline is not None and time.monotonic() >= deadline:
                return extra, False
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
