"""The four deterministic assertions of phase0-contracts.md §6."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.domain.models import PAGE_SIZE
from tests.engine.conftest import make_query
from tests.fixtures import tiny_pack

_PIECE_STATS = {
    piece_id: (attack_pts, slots)
    for rows in (
        tiny_pack.HEAD, tiny_pack.BODY, tiny_pack.ARMS, tiny_pack.WAIST, tiny_pack.LEGS
    )
    for piece_id, attack_pts, slots in rows
}
_DECO_STATS = {deco_id: (size, pts) for deco_id, size, pts in tiny_pack.DECORATIONS}

ALL_FIRST_PIECES = (1, 4, 7, 10, 13)


def collect_all_pages(service, session_id, query):
    """start_search + load_more until exhausted; returns (pages, all results)."""
    pages = []
    page = service.start_search(session_id, query)
    pages.append(page)
    while not page.exhausted and not page.partial and page.results:
        page = service.load_more(session_id, page.search_id)
        pages.append(page)
    return pages, [r for p in pages for r in p.results]


def achieved_attack(result) -> int:
    total = sum(_PIECE_STATS[pid][0] for pid in result.piece_ids)
    total += sum(_DECO_STATS[d.decoration_id][1] * d.count for d in result.decorations)
    return total


def test_assertion_1_all_first_pieces_15_attack_zero_decorations(search_service):
    _, results = collect_all_pages(search_service, "s1", make_query(min_points=10))

    match = [r for r in results if r.piece_ids == ALL_FIRST_PIECES]
    assert len(match) == 1
    result = match[0]
    assert result.decorations == ()
    # 4 + 3 + 3 + 2 + 3 = 15 attack, reported against the Attack Up (S) row.
    assert achieved_attack(result) == 15
    assert (1, 15) in result.active_skills


def test_assertion_2_every_result_meets_threshold_and_slot_capacity(search_service):
    query = make_query(min_points=10, weapon_slots=0)
    _, results = collect_all_pages(search_service, "s2", query)

    assert results, "fixture must yield at least one set for Attack >= 10"
    for result in results:
        assert achieved_attack(result) >= 10
        capacity = sum(_PIECE_STATS[pid][1] for pid in result.piece_ids) + query.weapon_slots
        used = sum(_DECO_STATS[d.decoration_id][0] * d.count for d in result.decorations)
        assert used <= capacity


def test_assertion_3_load_more_never_repeats_piece_ids(search_service):
    pages, results = collect_all_pages(search_service, "s3", make_query(min_points=10))

    seen = set()
    for result in results:
        assert result.piece_ids not in seen
        seen.add(result.piece_ids)
    assert pages[-1].exhausted
    assert all(len(p.results) <= PAGE_SIZE for p in pages)


def test_expand_equivalents_counts_cards_not_representatives(search_service):
    query = make_query(min_points=10, expand_equivalents=True)
    page = search_service.start_search("s-expand", query)
    page_cards = sum(r.equivalent_count() for r in page.results)
    assert page.shown_count == page_cards
    if page.remaining_count is not None:
        more = search_service.load_more("s-expand", page.search_id)
        more_cards = sum(r.equivalent_count() for r in more.results)
        assert more.shown_count == page.shown_count + more_cards
        if more.remaining_count is not None:
            assert more.remaining_count == page.remaining_count - more_cards


def test_assertion_4_impossible_query_is_exhausted_not_an_exception(search_service):
    page = search_service.start_search("s4", make_query(min_points=99))

    assert page.exhausted
    assert page.results == ()
    assert not page.partial
    # load_more on an exhausted search stays exhausted, still no exception.
    more = search_service.load_more("s4", page.search_id)
    assert more.exhausted
    assert more.results == ()


def test_start_search_persists_inf_rel_snapshot(search_service, user_data_repo):
    import json

    page = search_service.start_search("s5", make_query(min_points=10))
    state = user_data_repo.get_search_state(page.search_id)
    snapshot = json.loads(state["query_json"])["domain_snapshot"]
    assert set(snapshot["kinds"]) == {
        "head", "body", "arms", "waist", "legs", "decorations",
    }
    waist = snapshot["kinds"]["waist"]
    assert 11 in waist["inf_ids"]
    assert 11 not in waist["rel_ids"]
    assert 10 in waist["rel_ids"]
