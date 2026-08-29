"""Phase 0 search UI tests (phase0-contracts §5), against the real wired stack:
CpSatSearchService over the tiny-pack database (tests/conftest.py)."""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import PIECE_NAMES

SEARCH_FORM = {
    "skill_id": ["1", "", "", "", ""],
    "weapon_slots": "0",
    "gender": "m",
    "hunter_type": "blademaster",
    "hr": "",
    "village_stars": "",
    "sort": "defense",
    "allow_torso_inc": "on",
}

CARD_RE = re.compile(r'<div class="card ss-result')
PIECE_RE = re.compile(r'ss-piece-name">([^<]+)<')
SEARCH_ID_RE = re.compile(r'hx-post="/search/([^"]+)/more"')


@pytest.fixture()
def client(packed_db) -> TestClient:
    return TestClient(create_app())


def _cards(html: str) -> list[tuple[str, ...]]:
    """One tuple of 5 piece names per rendered result card."""
    chunks = html.split('<div class="card ss-result')[1:]
    return [tuple(unescape(name) for name in PIECE_RE.findall(chunk)) for chunk in chunks]


def test_index_renders_search_form(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert '<meta name="viewport"' in html
    # up to 5 named-skill picks (threshold rows, not tree + raw points)
    assert html.count('name="skill_id"') == 5
    assert 'name="skill_points"' not in html
    assert ">Attack Up (S)</option>" in html
    assert "Offensive" in html
    assert 'name="allow_torso_inc"' in html
    assert 'name="allow_dummy"' in html
    assert 'id="advanced-open"' in html
    assert 'id="advanced-modal"' in html
    assert 'disabled' in html.split('id="advanced-open"')[1].split(">")[0]
    assert 'name="excluded_piece_id"' not in html
    assert 'name="rel_piece_id"' not in html
    # weapon slots, gender, hunter type, HR/village filters
    assert 'name="weapon_slots"' in html
    assert 'name="gender"' in html
    assert 'name="hunter_type"' in html
    assert 'name="hr"' in html
    assert 'name="village_stars"' in html
    assert 'type="number"' not in html
    assert "Guild rank" in html
    assert "Village rank" in html
    assert "List every set" in html
    assert 'name="expand_equivalents"' in html
    assert ">9</option>" in html
    assert ">10</option>" not in html
    # vendored assets, no CDN framework links
    assert "/static/vendor/htmx.min.js" in html
    assert "/static/vendor/bootstrap.min.css" in html
    assert "tailwind" not in html.lower()


def test_start_search_returns_result_cards(client: TestClient):
    response = client.post("/games/mhfu/search", data=SEARCH_FORM)

    assert response.status_code == 200
    html = response.text
    cards = _cards(html)
    assert 1 <= len(cards) <= 10  # PAGE_SIZE
    for card in cards:
        assert len(card) == 5  # head/body/arms/waist/legs
        assert set(card) <= set(PIECE_NAMES.values())
    assert "Attack Up (S)" in html
    assert 'id="results-list"' in html
    assert 'id="results-summary"' in html
    assert "more to load" in html or "found." in html
    # load-more button wired per §5
    assert 'hx-target="#results-list"' in html
    assert 'hx-swap="beforeend"' in html
    assert SEARCH_ID_RE.search(html)
    assert 'id="advanced-open"' in html
    assert "disabled" not in html.split('id="advanced-open"')[1].split(">")[0]
    assert 'name="rel_piece_id"' in html
    assert 'name="rel_decoration_id"' in html
    assert "Chain Faulds" in html
    assert 'data-skyline="0"' in html
    assert 'name="advanced_domain"' in html
    assert "ss-pip-1" not in html
    assert "ss-pip-2" not in html
    assert "ss-pip-3" not in html
    assert "ss-pip-empty" in html or "ss-pip-filled" in html
    assert "free socket" in html


def test_load_more_updates_remaining_count(client: TestClient):
    first = client.post("/games/mhfu/search", data=SEARCH_FORM)
    assert first.status_code == 200
    assert "results-summary" in first.text
    if "more to load" not in first.text:
        assert "found." in first.text
        return
    search_id = SEARCH_ID_RE.search(first.text).group(1)
    more = client.post(f"/search/{search_id}/more")
    assert more.status_code == 200
    assert 'id="results-summary"' in more.text
    assert 'hx-swap-oob="true"' in more.text
    assert "more to load" in more.text or "found." in more.text


def test_load_more_pages_until_exhausted_without_repeats(client: TestClient):
    first = client.post("/games/mhfu/search", data=SEARCH_FORM)
    search_id = SEARCH_ID_RE.search(first.text).group(1)

    seen = set(_cards(first.text))
    assert seen
    exhausted = False
    # The tiny pack has a few dozen feasible sets; 40 pages is generous.
    for _ in range(40):
        page = client.post(f"/search/{search_id}/more")
        assert page.status_code == 200
        # fragment updates the load-more control out-of-band
        assert 'id="load-more"' in page.text
        assert 'hx-swap-oob="true"' in page.text
        new_cards = _cards(page.text)
        assert not (seen & set(new_cards))  # pagination never repeats a set
        seen |= set(new_cards)
        if "All sets found" in page.text:
            # The final page may carry the last cards alongside the marker.
            exhausted = True
            assert "Load more sets" not in page.text
            break
    assert exhausted, "tiny-pack search did not exhaust within 40 pages"


def test_impossible_query_renders_empty_exhausted_state(client: TestClient):
    response = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_id": ["2", "", "", "", ""]},
    )

    assert response.status_code == 200
    html = response.text
    assert "No sets activate those skills" in html
    assert "All sets found" in html
    assert "0 sets found" in html
    assert 'class="card ss-result' not in html


def test_vendored_static_assets_are_served(client: TestClient):
    for path in (
        "/static/vendor/bootstrap.min.css",
        "/static/vendor/bootstrap.bundle.min.js",
        "/static/vendor/htmx.min.js",
        "/static/vendor/alpine.min.js",
        "/static/app.css",
    ):
        assert client.get(path).status_code == 200, path


def test_search_lists_every_equivalent_when_requested(client: TestClient):
    response = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "expand_equivalents": "on"},
    )
    assert response.status_code == 200
    assert "Every equivalent piece is its own set." in response.text
    cards = _cards(response.text)
    assert cards
    summary = unescape(response.text)
    if "shown —" in summary:
        shown = int(re.search(r"(\d+) shown", summary).group(1))
        assert shown == len(cards)
    elif "found." in summary:
        shown = int(re.search(r"(\d+) sets? found", summary).group(1))
        assert shown == len(cards)


def test_search_rejects_rank_above_pack_cap(client: TestClient):
    too_high = client.post("/games/mhfu/search", data={**SEARCH_FORM, "hr": "10"})
    assert too_high.status_code == 422
    village = client.post("/games/mhfu/search", data={**SEARCH_FORM, "village_stars": "99"})
    assert village.status_code == 422


def test_search_requires_at_least_one_skill(client: TestClient):
    response = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_id": ["", "", "", "", ""]},
    )
    assert response.status_code == 422


def test_search_rejects_unknown_and_invented_skills(client: TestClient):
    unknown = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_id": ["99999", "", "", "", ""]},
    )
    assert unknown.status_code == 422
    garbage = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_id": ["nope", "", "", "", ""]},
    )
    assert garbage.status_code == 422


def test_search_excludes_omitted_pieces_from_results(client: TestClient):
    response = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "excluded_piece_id": ["1"]},
    )
    assert response.status_code == 200
    cards = _cards(response.text)
    assert cards
    assert all("Leather Helm" not in card for card in cards)


def test_advanced_endpoint_lists_inf_and_checks_rel(client: TestClient):
    first = client.post("/games/mhfu/search", data=SEARCH_FORM)
    search_id = SEARCH_ID_RE.search(first.text).group(1)
    response = client.get(f"/search/{search_id}/advanced")
    assert response.status_code == 200
    html = response.text
    names = set(re.findall(r'for="adv-[^"]+">([^<]+)<', html))
    assert "Chain Faulds" in names
    assert "Leather Faulds" in names
    # Dominated waist 11 is listed but not default-checked.
    assert 'id="adv-waist-11"' in html
    waist_11 = html.split('id="adv-waist-11"')[1].split(">", 1)[0]
    assert "checked" not in waist_11
    waist_10 = html.split('id="adv-waist-10"')[1].split(">", 1)[0]
    assert "checked" in waist_10


def test_advanced_force_include_checks_dominated_piece(client: TestClient):
    response = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "forced_piece_id": ["11"]},
    )
    assert response.status_code == 200
    waist_11 = response.text.split('id="adv-waist-11"')[1].split(">", 1)[0]
    assert "checked" in waist_11


def test_unknown_advanced_search_is_404(client: TestClient):
    assert client.get("/search/does-not-exist/advanced").status_code == 404


def test_index_lists_pack_scoped_categories(client: TestClient):
    html = client.get("/").text
    assert "Offensive" in html
    assert "Treasure Hunting" not in html  # tiny pack, not a hardcoded MHFU list
