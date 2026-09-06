"""Concurrent start_search must not deadlock or stack unbounded prefetch."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event

import pytest

from app.engine.service import CpSatSearchService, SearchBusyError
from tests.engine.conftest import make_query


def test_two_sessions_start_search_no_deadlock(search_service):
    query = make_query(min_points=10)

    def run(session_id: str):
        return search_service.start_search(session_id, query)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, "sess-a"), pool.submit(run, "sess-b")]
        pages = [f.result(timeout=30) for f in as_completed(futures)]

    assert all(p.search_id for p in pages)
    assert all(p.results or p.exhausted or p.partial for p in pages)


def test_solve_does_not_hold_service_lock(user_data_repo, tiny_pack_data, monkeypatch):
    entered = Event()
    release = Event()
    from app.engine import service as svc_mod

    real = svc_mod.solve_one

    def gated(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=2)
        return real(*args, **kwargs)

    monkeypatch.setattr(svc_mod, "solve_one", gated)
    service = CpSatSearchService(user_data_repo, lambda game: tiny_pack_data, time_limit_ms=2000)

    def run():
        return service.start_search("lock-sess", make_query(min_points=10))

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(run)
        assert entered.wait(timeout=2)
        acquired = service._lock.acquire(timeout=0.5)
        assert acquired, "service lock must not be held during CP-SAT"
        service._lock.release()
        release.set()
        page = fut.result(timeout=30)
    assert page.search_id


def test_busy_when_slot_held(user_data_repo, tiny_pack_data):
    service = CpSatSearchService(
        user_data_repo,
        lambda game: tiny_pack_data,
        time_limit_ms=2000,
        queue_wait_s=0.05,
    )
    assert service._slots.acquire(blocking=False)
    try:
        with pytest.raises(SearchBusyError):
            service.start_search("busy", make_query(min_points=10))
    finally:
        service._slots.release()
