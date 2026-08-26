"""Phase 0 search UI tests (phase0-contracts §5/§6, against MockSearchService)."""

import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

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


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_index_renders_search_form(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert '<meta name="viewport"' in html
    # up to 5 skill picks
    assert html.count('name="skill_tree"') == 5
    assert html.count('name="skill_points"') == 5
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
    # one canned card: the all-first-pieces fixture set
    assert html.count("ss-result") >= 1
    for name in (
        "Leather Helm",
        "Leather Mail",
        "Leather Vambraces",
        "Leather Faulds",
        "Leather Greaves",
    ):
        assert name in html
    assert "Attack Up (S)" in html
    assert 'id="results-list"' in html
    # load-more button wired per §5
    assert 'hx-target="#results-list"' in html
    assert 'hx-swap="beforeend"' in html
    assert re.search(r'hx-post="/search/[^"]+/more"', html)


def test_load_more_appends_cards_and_reports_exhausted(client: TestClient):
    first = client.post("/games/mhfu/search", data=SEARCH_FORM)
    search_id = re.search(r'hx-post="/search/([^"]+)/more"', first.text).group(1)

    second = client.post(f"/search/{search_id}/more")

    assert second.status_code == 200
    html = second.text
    # fragment updates the load-more control out-of-band
    assert 'id="load-more"' in html
    assert 'hx-swap-oob="true"' in html
    # page 2 of the mock is exhausted: no cards, no further button
    assert "All sets found" in html
    assert "Load more sets" not in html
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
