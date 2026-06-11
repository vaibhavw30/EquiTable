# backend_ml/tests/agent/test_graph.py
"""Tests for the parent refresh graph (Task 17).

Tests:
- end-to-end run: 3 pantries seeded → all succeed, metrics written
- budget exhaustion: CostTracker(budget_usd=0.0) → all skipped_budget
- one-source-crash (robustness enhancement): subgraph stub raises for one URL,
  run still completes with that source marked "failed", others succeed
"""
from datetime import datetime, timezone, timedelta
from agent.cost import CostTracker
from agent.subgraph import build_extraction_subgraph
from agent.graph import build_refresh_graph
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.curator import make_curator_node
from agent.nodes.metrics import make_update_metrics_node
from agent.state import ExtractionResult
from tests.agent.conftest import FakeStructuredModel, FakeModelFactory, FakeScraper

GOOD = {"status": "OPEN", "hours_notes": "x", "hours_today": "x",
        "eligibility_rules": ["Open to all"], "is_id_required": False,
        "residency_req": None, "special_notes": None, "confidence": 8}


def _factory():
    return FakeModelFactory([FakeStructuredModel(scripted=[ExtractionResult(**GOOD)])])


async def _seed(test_db, n):
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    for i in range(n):
        await test_db["pantries"].insert_one(
            {"name": f"p{i}", "address": "a", "lat": 1, "lng": 2, "hours_notes": "OLD",
             "status": "UNKNOWN", "source_url": f"https://p{i}.org", "last_updated": old})


async def test_refresh_graph_end_to_end(test_db):
    await _seed(test_db, 3)
    tracker = CostTracker(budget_usd=1.0)
    sub = build_extraction_subgraph(FakeScraper(), _factory(), tracker, lambda: "SYS", db=test_db)
    app = build_refresh_graph(
        make_load_sources_node(db=test_db), make_curator_node(ranker=None),
        sub, tracker, make_update_metrics_node(db=test_db))
    final = await app.ainvoke({"run_id": "t1", "cost_budget_usd": 1.0})
    assert final["results"]
    assert all(r["outcome"] == "success" for r in final["results"])
    # metrics written for each source
    assert await test_db["source_metrics"].count_documents({}) == 3


async def test_budget_exhaustion_skips_remaining(test_db):
    await _seed(test_db, 3)
    tracker = CostTracker(budget_usd=0.0)   # already exhausted
    sub = build_extraction_subgraph(FakeScraper(), _factory(), tracker, lambda: "SYS", db=test_db)
    app = build_refresh_graph(
        make_load_sources_node(db=test_db), make_curator_node(ranker=None),
        sub, tracker, make_update_metrics_node(db=test_db))
    final = await app.ainvoke({"run_id": "t2", "cost_budget_usd": 0.0})
    assert all(r["outcome"] == "skipped_budget" for r in final["results"])


# ── Robustness enhancement: one-source-crash must not abort the whole batch ──

class _CrashingSubgraph:
    """Fake subgraph that raises for a specific URL, succeeds for others."""
    def __init__(self, crash_url: str, good_result: dict):
        self._crash_url = crash_url
        self._good_result = good_result

    async def ainvoke(self, state: dict) -> dict:
        if state["source_url"] == self._crash_url:
            raise RuntimeError(f"Simulated crash for {self._crash_url}")
        return self._good_result


async def test_one_source_crash_does_not_abort_run(test_db):
    """A subgraph that raises for one URL must not crash the whole gather."""
    await _seed(test_db, 3)  # p0, p1, p2

    good_subgraph_result = {
        "outcome": "success",
        "latency_ms": 100.0,
        "model_tier": 0,
        "validation_errors": [],
    }
    # p1.org will crash; p0 and p2 should succeed
    crashing_sub = _CrashingSubgraph(
        crash_url="https://p1.org",
        good_result=good_subgraph_result,
    )

    tracker = CostTracker(budget_usd=1.0)
    app = build_refresh_graph(
        make_load_sources_node(db=test_db), make_curator_node(ranker=None),
        crashing_sub, tracker, make_update_metrics_node(db=test_db))

    final = await app.ainvoke({"run_id": "t3", "cost_budget_usd": 1.0})

    results_by_url = {r["source_url"]: r for r in final["results"]}

    # The crashing source must be marked "failed", not propagate an exception
    assert results_by_url["https://p1.org"]["outcome"] == "failed"
    assert results_by_url["https://p1.org"]["latency_ms"] == 0.0
    assert results_by_url["https://p1.org"]["model_tier"] is None

    # The other two sources must have succeeded
    assert results_by_url["https://p0.org"]["outcome"] == "success"
    assert results_by_url["https://p2.org"]["outcome"] == "success"

    # All 3 results present (run did NOT abort)
    assert len(final["results"]) == 3
