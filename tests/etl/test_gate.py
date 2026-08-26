"""Validation-gate tests: the real suite must pass; tampered suites must fail."""

import copy

import yaml

from app.etl.gate import Gate, run_gate
from tests.etl.conftest import PACK_DIR


def test_known_query_suite_passes(etl_db):
    repo, game_id, _ = etl_db
    passed, results = run_gate(repo, game_id, PACK_DIR)
    failures = [f"{r.name}: {r.detail}" for r in results if not r.ok]
    assert passed, failures


def test_gate_detects_tampered_expectation(etl_db):
    repo, game_id, _ = etl_db
    suite = yaml.safe_load((PACK_DIR / "known_queries.yaml").read_text())
    tampered = copy.deepcopy(suite)
    for query in tampered["queries"]:
        if query["name"].startswith("Chain Helm"):
            query["expect"]["slots"] = 3  # actually 1 ("O--")
    results = Gate(repo, game_id).run(tampered)
    assert not all(r.ok for r in results)
    failed = next(r for r in results if not r.ok)
    assert "Chain Helm" in failed.name


def test_gate_detects_wrong_row_counts(etl_db):
    repo, game_id, _ = etl_db
    results = Gate(repo, game_id).run({"row_counts": {"armor_pieces": 1}})
    assert results[0].ok is False
    assert "armor_pieces" in results[0].detail
