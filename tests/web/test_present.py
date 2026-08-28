"""Render helpers: equivalence expansion for 'list every set'."""

from app.domain.models import ArmorSetResult
from app.web.present import expand_equivalent_results, page_context
from app.domain.models import SearchPage


class _Resolver:
    def armor_piece(self, piece_id: int) -> dict:
        return {"name": f"Piece {piece_id}", "rarity": 1, "defense": piece_id}

    def decoration_name(self, decoration_id: int) -> str:
        return f"D{decoration_id}"

    def skill_name(self, skill_id: int) -> str:
        return "Attack Up (S)"


def _grouped() -> ArmorSetResult:
    return ArmorSetResult(
        piece_ids=(1, 4, 7, 10, 13),
        alternates=((1, 2), (4,), (7,), (10,), (13,)),
        decorations=(),
        charm_id=None,
        active_skills=((1, 15),),
        spare_slots=(0, 0, 0),
        defense=15,
    )


def test_expand_equivalent_results_makes_one_card_per_combo():
    cards = expand_equivalent_results(_grouped(), _Resolver())
    assert [c.piece_ids for c in cards] == [(1, 4, 7, 10, 13), (2, 4, 7, 10, 13)]
    assert all(c.alternates == tuple((pid,) for pid in c.piece_ids) for c in cards)


def test_page_context_grouped_keeps_one_card():
    page = SearchPage(
        search_id="s", results=(_grouped(),), partial=False, exhausted=True,
        shown_count=1, remaining_count=0,
    )
    ctx = page_context(page, _Resolver(), expand_equivalents=False)
    assert len(ctx["results"]) == 1
    assert len(ctx["results"][0]["pieces"][0]["alternates"]) == 2


def test_page_context_expanded_splits_lookalikes():
    page = SearchPage(
        search_id="s", results=(_grouped(),), partial=False, exhausted=True,
        shown_count=1, remaining_count=0,
    )
    ctx = page_context(page, _Resolver(), expand_equivalents=True)
    assert len(ctx["results"]) == 2
    assert {c["pieces"][0]["name"] for c in ctx["results"]} == {"Piece 1", "Piece 2"}
    assert all(len(c["pieces"][0]["alternates"]) == 1 for c in ctx["results"])
