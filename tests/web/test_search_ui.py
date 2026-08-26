"""Phase 0 search UI tests (phase0-contracts §5), against the real wired stack:
CpSatSearchService over the tiny-pack database (tests/conftest.py)."""

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import PIECE_NAMES

SEARCH_FORM = {
    "skill_tree": ["1", "", "", "", ""],
    "skill_points": ["10", "", "", "", ""],
    "weapon_slots": "0",
    "gender": "m",
    "hunter_type": "blademaster",
    "hr": "",
    "village_stars": "",
    "sort": "defense",
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
    # up to 5 skill picks
    assert html.count('name="skill_tree"') == 5
    assert html.count('name="skill_points"') == 5
    # the tiny pack's tree is a real form option
    assert ">Attack</option>" in html
    # weapon slots, gender, hunter type, HR/village filters
    assert 'name="weapon_slots"' in html
    assert 'name="gender"' in html
    assert 'name="hunter_type"' in html
    assert 'name="hr"' in html
    assert 'name="village_stars"' in html
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
    # load-more button wired per §5
    assert 'hx-target="#results-list"' in html
    assert 'hx-swap="beforeend"' in html
    assert SEARCH_ID_RE.search(html)


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
        data={**SEARCH_FORM, "skill_points": ["99", "", "", "", ""]},
    )

    assert response.status_code == 200
    html = response.text
    assert "No sets activate those skills" in html
    assert "All sets found" in html
    assert "ss-result" not in html


def test_vendored_static_assets_are_served(client: TestClient):
    for path in (
        "/static/vendor/bootstrap.min.css",
        "/static/vendor/bootstrap.bundle.min.js",
        "/static/vendor/htmx.min.js",
        "/static/vendor/alpine.min.js",
        "/static/app.css",
    ):
        assert client.get(path).status_code == 200, path


def test_search_requires_at_least_one_skill(client: TestClient):
    response = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_tree": ["", "", "", "", ""],
              "skill_points": ["", "", "", "", ""]},
    )
    assert response.status_code == 422
