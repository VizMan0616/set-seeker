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
    assert 'hx-post="/search"' in html
    assert 'name="game"' in html
    assert 'id="advanced-open"' in html
    assert 'id="advanced-modal"' in html
    assert "disabled" in html.split('id="advanced-open"')[1].split(">")[0]
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


def test_search_picker_route_uses_game_field(client: TestClient):
    response = client.post("/search", data={**SEARCH_FORM, "game": "mhfu"})
    assert response.status_code == 200
    assert "ss-result" in response.text or "ss-empty" in response.text
    assert "Unknown game" not in response.text


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
    assert 'hx-trigger="revealed"' in first.text
    assert "ss-scroll-sentinel" in first.text


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


def test_search_clamps_rank_above_pack_cap(client: TestClient):
    too_high = client.post("/games/mhfu/search", data={**SEARCH_FORM, "hr": "10"})
    assert too_high.status_code == 200
    assert "ss-result" in too_high.text or "ss-empty" in too_high.text
    village = client.post("/games/mhfu/search", data={**SEARCH_FORM, "village_stars": "99"})
    assert village.status_code == 200


def test_search_rejects_six_skills_on_mhfu(packed_db, client: TestClient):
    ids = ["1"]
    for n in range(5):
        tree_id = 50 + n
        skill_id = 50 + n
        packed_db.create_skill_tree(
            id=tree_id,
            game_id=1,
            name_en=f"Extra{n}",
            name_ja=f"Extra{n}",
        )
        packed_db.create_skill(
            id=skill_id,
            tree_id=tree_id,
            name_en=f"Extra Skill {n}",
            points=10,
        )
        ids.append(str(skill_id))
    too_many = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_id": ids},
    )
    assert too_many.status_code == 200
    assert "Choose between 1 and 5 skills" in too_many.text
    response = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_id": ["", "", "", "", ""]},
    )
    assert response.status_code == 200
    assert "Choose between 1 and 5 skills" in response.text


def test_search_rejects_unknown_and_invented_skills(client: TestClient):
    unknown = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_id": ["99999", "", "", "", ""]},
    )
    assert unknown.status_code == 200
    assert "Unknown skill" in unknown.text
    garbage = client.post(
        "/games/mhfu/search",
        data={**SEARCH_FORM, "skill_id": ["nope", "", "", "", ""]},
    )
    assert garbage.status_code == 200
    assert "Invalid skill" in garbage.text


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


def test_torso_inc_checkbox_uses_skill_tree_name(packed_db):
    """Label comes from the empty-threshold tree, not a hardcoded game id."""
    import json

    packed_db.create_skill_tree(
        id=20,
        game_id=1,
        name_en="Torso Inc",
        name_ja="胴系統倍加",
    )
    packed_db.create_armor_piece(
        id=80,
        game_id=1,
        slot=4,
        name_en="Torso Greaves",
        rarity=1,
        slots=0,
        gender=2,
        hunter_type=2,
        defense=1,
        max_defense=1,
        res_fire=0,
        res_water=0,
        res_ice=0,
        res_thunder=0,
        res_dragon=0,
        torso_inc=True,
    )
    html = TestClient(create_app()).get("/").text
    catalogs = json.loads(html.split('id="ss-catalogs">', 1)[1].split("</script>", 1)[0])
    assert catalogs["mhfu"]["torso_inc_name"] == "Torso Inc"
    assert "Allow Torso Inc" in html


def test_health_ok(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.text == "ok"


def test_health_during_inflight_search(packed_db, monkeypatch):
    """GET /health must complete while a solve is blocked (event loop free)."""
    import socket
    import threading
    import time
    from threading import Event

    import httpx
    import uvicorn

    from app.engine import service as svc_mod

    entered = Event()
    release = Event()
    real = svc_mod.solve_one

    def gated(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return real(*args, **kwargs)

    monkeypatch.setattr(svc_mod, "solve_one", gated)
    app = create_app()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    host, port = sock.getsockname()
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.time() + 5
        while time.time() < deadline:
            if server.started:
                break
            time.sleep(0.02)
        assert server.started
        base = f"http://{host}:{port}"
        search_exc: list[BaseException] = []

        def do_search() -> None:
            try:
                with httpx.Client(timeout=15) as ac:
                    r = ac.post(f"{base}/games/mhfu/search", data=SEARCH_FORM)
                    assert r.status_code == 200
            except BaseException as exc:  # noqa: BLE001 — surface in main thread
                search_exc.append(exc)

        searcher = threading.Thread(target=do_search)
        searcher.start()
        assert entered.wait(timeout=5)
        with httpx.Client(timeout=5) as ac:
            health = ac.get(f"{base}/health")
        assert health.status_code == 200
        assert health.text == "ok"
        release.set()
        searcher.join(timeout=15)
        assert not searcher.is_alive()
        assert not search_exc
    finally:
        server.should_exit = True
        thread.join(timeout=5)
