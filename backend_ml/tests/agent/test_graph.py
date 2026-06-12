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


# ── Budget soft-cap crossover test ───────────────────────────────────────────

async def test_budget_crosses_midrun_skips_remainder(test_db):
    """Pin the soft-cap contract: admitted sources can overrun by ≤ MAX_CONCURRENT × per-source-cost.

    A 'spending subgraph' spends ~$0.20 per call by calling cost_tracker.add_usage
    with enough tokens to reach that cost.  With budget_usd=0.50 and 8 sources,
    at most MAX_CONCURRENT sources can run before the budget gate flips — the rest
    are marked skipped_budget.
    """
    from agent.config import MAX_CONCURRENT, MODEL_PRICING
    import math

    await _seed(test_db, 8)

    tracker = CostTracker(budget_usd=0.50)

    # Compute N so that one call spends exactly ~$0.20 using gemini-3.5-flash input pricing
    in_price_per_1m, _ = MODEL_PRICING["gemini-3.5-flash"]   # 0.30 USD/1M tokens
    per_call_usd = 0.20
    n_input_tokens = math.ceil(per_call_usd / (in_price_per_1m / 1_000_000))

    class _SpendingSubgraph:
        """Fake subgraph that charges ~$0.20 per invocation via the shared tracker."""
        def __init__(self, cost_tracker):
            self._tracker = cost_tracker

        async def ainvoke(self, state: dict) -> dict:
            self._tracker.add_usage("gemini-3.5-flash",
                                    input_tokens=n_input_tokens,
                                    output_tokens=0)
            return {
                "outcome": "success",
                "latency_ms": 10.0,
                "model_tier": 0,
                "validation_errors": [],
            }

    spending_sub = _SpendingSubgraph(tracker)

    app = build_refresh_graph(
        make_load_sources_node(db=test_db),
        make_curator_node(ranker=None),
        spending_sub,
        tracker,
        make_update_metrics_node(db=test_db),
    )
    final = await app.ainvoke({"run_id": "t_crossover", "cost_budget_usd": 0.50})

    outcomes = [r["outcome"] for r in final["results"]]

    # At least one source ran and at least one was skipped
    assert "success" in outcomes, "Expected at least one source to run successfully"
    assert "skipped_budget" in outcomes, "Expected at least one source to be skipped_budget"

    # Realized spend must not exceed the documented bound: MAX_CONCURRENT × per_call_usd
    epsilon = 0.001   # floating-point tolerance
    max_allowed_spend = MAX_CONCURRENT * per_call_usd + epsilon
    assert tracker.spent_usd <= max_allowed_spend, (
        f"Realized overrun {tracker.spent_usd:.4f} exceeds documented bound "
        f"MAX_CONCURRENT({MAX_CONCURRENT}) × per_call({per_call_usd}) = {MAX_CONCURRENT * per_call_usd:.2f}"
    )


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


# ── Mixed-outcome end-to-end through the REAL subgraph ───────────────────────

class _SelectiveScraper:
    """Returns None for scrapefail URLs, RETRYFAIL-tagged markdown for retryfail
    URLs, and valid pantry markdown for all others."""
    async def scrape_url(self, url: str):
        if "scrapefail" in url:
            return None
        if "retryfail" in url:
            return "# Pantry\nRETRYFAIL — always invalid"
        return "# Pantry\nMon-Fri 9am-5pm. No ID required. Open to all."

    async def scrape_with_provenance(self, url: str):
        from services.scraper import ScrapeResult
        md = await self.scrape_url(url)
        return ScrapeResult(md, "crawl4ai" if md else "none")


class _MarkerModel:
    """Structured-output model whose behaviour depends on message content.

    Inspects the last HumanMessage.  If ``RETRYFAIL`` is in the content,
    returns confidence=99 (invalid range) on every call.  Otherwise returns
    a fully-valid ExtractionResult.
    """
    def __init__(self):
        self.calls = 0

    async def ainvoke(self, messages):
        from tests.agent.conftest import FakeRawMessage
        self.calls += 1
        content = messages[-1].content if messages else ""
        if "RETRYFAIL" in content:
            parsed = ExtractionResult(
                status="OPEN", hours_notes="x", hours_today="x",
                eligibility_rules=["Open to all"], is_id_required=False,
                residency_req=None, special_notes=None, confidence=99,  # invalid
            )
        else:
            parsed = ExtractionResult(
                status="OPEN", hours_notes="Mon-Fri 9am-5pm", hours_today="9am-5pm",
                eligibility_rules=["Open to all"], is_id_required=False,
                residency_req=None, special_notes=None, confidence=8,
            )
        return {"raw": FakeRawMessage(), "parsed": parsed, "parsing_error": None}


class _MarkerModelFactory:
    """Returns the same _MarkerModel instance for every tier."""
    def __init__(self):
        self._model = _MarkerModel()

    def get(self, tier):
        return self._model

    def name_for_tier(self, tier):
        from agent.config import model_for_tier
        return model_for_tier(tier)


async def test_parent_run_mixed_outcomes(test_db):
    """One parent-graph invocation that exercises success, scrape-failure, and
    retry-exhaustion-failure through the REAL extraction subgraph.

    Sources:
        good.org      → scrapes fine, extraction valid → outcome="success"
        scrapefail.org → scrape returns None → outcome="failed",
                         last_error ~ "scrape returned no content"
        retryfail.org  → scrapes fine but model always returns confidence=99
                         (validation fails) → retries exhausted → persist refuses
                         to write → outcome="failed", DB doc unchanged
    """
    from datetime import datetime, timezone, timedelta

    old = datetime.now(timezone.utc) - timedelta(hours=48)
    urls = ["https://good.org", "https://scrapefail.org", "https://retryfail.org"]
    for url in urls:
        await test_db["pantries"].insert_one({
            "name": url.split("//")[1], "address": "a", "lat": 1.0, "lng": 2.0,
            "hours_notes": "OLD", "status": "UNKNOWN", "source_url": url,
            "confidence": 5, "last_updated": old,
        })

    tracker = CostTracker(budget_usd=10.0)
    sub = build_extraction_subgraph(
        _SelectiveScraper(), _MarkerModelFactory(), tracker, lambda: "SYS", db=test_db,
    )
    app = build_refresh_graph(
        make_load_sources_node(db=test_db),
        make_curator_node(ranker=None),
        sub,
        tracker,
        make_update_metrics_node(db=test_db),
    )
    final = await app.ainvoke({"run_id": "mixed", "cost_budget_usd": 10.0})

    by_url = {r["source_url"]: r for r in final["results"]}

    # ── good.org → success ────────────────────────────────────────────────────
    assert by_url["https://good.org"]["outcome"] == "success", (
        f"good.org expected 'success', got {by_url['https://good.org']['outcome']!r}"
    )

    # ── scrapefail.org → failed (scrape returned no content) ─────────────────
    scrapefail = by_url["https://scrapefail.org"]
    assert scrapefail["outcome"] == "failed", (
        f"scrapefail.org expected 'failed', got {scrapefail['outcome']!r}"
    )
    sm_scrape = await test_db["source_metrics"].find_one(
        {"source_url": "https://scrapefail.org"}
    )
    assert sm_scrape is not None, "source_metrics should exist for scrapefail.org"
    assert sm_scrape.get("last_error") and "scrape" in sm_scrape["last_error"].lower(), (
        f"Expected last_error to mention 'scrape', got: {sm_scrape.get('last_error')!r}"
    )

    # ── retryfail.org → failed (retries exhausted, DB doc NOT updated) ────────
    retryfail = by_url["https://retryfail.org"]
    assert retryfail["outcome"] == "failed", (
        f"retryfail.org expected 'failed', got {retryfail['outcome']!r}"
    )
    # Confidence must NOT have been written (persist refuses on validation errors)
    doc_rf = await test_db["pantries"].find_one({"source_url": "https://retryfail.org"})
    assert doc_rf["confidence"] == 5, (
        f"retryfail.org DB confidence should be unchanged (5), got {doc_rf.get('confidence')}"
    )

    # ── source_metrics written for all three sources ──────────────────────────
    assert await test_db["source_metrics"].count_documents({}) == 3

    sm_good = await test_db["source_metrics"].find_one({"source_url": "https://good.org"})
    assert sm_good is not None
    assert sm_good["successes"] == 1 and sm_good["failures"] == 0

    sm_rf = await test_db["source_metrics"].find_one({"source_url": "https://retryfail.org"})
    assert sm_rf is not None
    assert sm_rf["failures"] == 1 and sm_rf["successes"] == 0


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
    # latency_ms is now the real wall-time elapsed before the exception was raised
    assert results_by_url["https://p1.org"]["latency_ms"] >= 0.0
    assert results_by_url["https://p1.org"]["model_tier"] is None

    # The other two sources must have succeeded
    assert results_by_url["https://p0.org"]["outcome"] == "success"
    assert results_by_url["https://p2.org"]["outcome"] == "success"

    # All 3 results present (run did NOT abort)
    assert len(final["results"]) == 3
