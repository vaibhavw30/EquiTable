"""End-to-end refresh smoke test (offline/deterministic).

This test does NOT call run_refresh() (which hits real Gemini + real
Chromium scraping). Instead it builds the graph directly with fakes:

  - FakeScraper — returns static markdown
  - FakeModelFactory / FakeStructuredModel — returns a scripted ExtractionResult
  - CostTracker(1.0) — real budget accounting

Smoke criteria (per the plan's Task 19 spec):
  1. All 5 seeded stale pantries produce outcome == "success"
  2. tracker.spent_usd <= 1.0  (budget not exceeded)
  3. Every persisted pantry has 1 <= confidence <= 10 and a valid status

Also includes an import-sanity check that verifies cli.py is importable and
run_refresh is a coroutine function — catches wiring/syntax errors without
making any network calls.
"""

import inspect
from datetime import datetime, timezone, timedelta

import pytest

from agent.cost import CostTracker
from agent.graph import build_refresh_graph
from agent.nodes.curator import make_curator_node
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.metrics import make_update_metrics_node
from agent.state import ExtractionResult
from agent.subgraph import build_extraction_subgraph
from tests.agent.conftest import FakeScraper, FakeStructuredModel, FakeModelFactory

# A valid extraction that passes the validator
GOOD = {
    "status": "OPEN",
    "hours_notes": "Mon-Fri 9-5",
    "hours_today": "9-5",
    "eligibility_rules": ["Open to all"],
    "is_id_required": False,
    "residency_req": None,
    "special_notes": None,
    "confidence": 7,
}

VALID_STATUSES = {"OPEN", "CLOSED", "WAITLIST", "UNKNOWN"}


# ── Import / wiring sanity check ─────────────────────────────────────────────

def test_cli_imports_cleanly_and_run_refresh_is_coroutine():
    """Verify cli.py imports without errors and run_refresh is async.

    This catches wiring/syntax errors in cli.py without making any network calls.
    """
    from agent.cli import run_refresh, main  # noqa: F401 (imported for side-effect check)
    assert inspect.iscoroutinefunction(run_refresh), (
        "run_refresh must be a coroutine function (defined with async def)"
    )


# ── End-to-end smoke test (fakes, no network) ─────────────────────────────────

async def test_refresh_smoke(test_db):
    """Full graph invocation with 5 stale pantries and fakes.

    Asserts:
    - All 5 pantries have outcome == "success"
    - Budget not exceeded
    - Every persisted pantry has a valid confidence (1-10) and status
    """
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    for i in range(5):
        await test_db["pantries"].insert_one({
            "name": f"smoke_pantry_{i}",
            "address": f"{i} Main St",
            "lat": 33.7 + i * 0.01,
            "lng": -84.4 + i * 0.01,
            "hours_notes": "OLD",
            "status": "UNKNOWN",
            "source_url": f"https://smoke{i}.org",
            "city": "Atlanta",
            "state": "GA",
            "last_updated": old,
        })

    tracker = CostTracker(budget_usd=1.0)
    factory = FakeModelFactory([
        # One scripted entry is enough: FakeStructuredModel clamps/round-robins to its
        # last entry, so this single ExtractionResult serves all 5 pantry invocations.
        FakeStructuredModel(scripted=[ExtractionResult(**GOOD)])
    ])
    sub = build_extraction_subgraph(
        FakeScraper(), factory, tracker, lambda: "SYSTEM PROMPT", db=test_db
    )
    app = build_refresh_graph(
        make_load_sources_node(db=test_db),
        make_curator_node(ranker=None),
        sub,
        tracker,
        make_update_metrics_node(db=test_db),
    )

    final = await app.ainvoke({"run_id": "smoke", "cost_budget_usd": 1.0})

    # Spec criterion 1: all 5 results with outcome == "success"
    results = final["results"]
    assert len(results) == 5, f"Expected 5 results, got {len(results)}"
    for r in results:
        assert r["outcome"] == "success", (
            f"Expected outcome='success' for {r['source_url']}, got {r['outcome']!r}"
        )

    # Spec criterion 2: within budget
    assert tracker.spent_usd <= 1.0, (
        f"Budget exceeded: spent_usd={tracker.spent_usd}"
    )

    # Spec criterion 3: persisted pantries have valid confidence + status
    async for doc in test_db["pantries"].find({"source_url": {"$regex": "^https://smoke"}}):
        assert 1 <= doc["confidence"] <= 10, (
            f"confidence out of range for {doc['source_url']}: {doc['confidence']}"
        )
        assert doc["status"] in VALID_STATUSES, (
            f"invalid status for {doc['source_url']}: {doc['status']!r}"
        )
