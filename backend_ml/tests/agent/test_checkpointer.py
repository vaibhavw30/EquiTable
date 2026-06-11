# backend_ml/tests/agent/test_checkpointer.py
"""Resume test for the MongoDB-backed LangGraph checkpointer.

Verifies:
1. The refresh graph runs to completion with the checkpointer attached.
2. After the run, ``app.aget_state(cfg)`` retrieves the persisted state from
   MongoDB under the same thread_id (the "resume contract").

Deterministic / offline: uses FakeScraper + FakeModelFactory so no real LLM
or HTTP calls are made.  Checkpoint collections are written into the
``equitable_test`` database so the ``test_db`` fixture's drop-on-teardown
cleans them up automatically.
"""

import os
from datetime import datetime, timezone, timedelta

import pytest

from agent.checkpointer import mongo_checkpointer
from agent.cost import CostTracker
from agent.graph import build_refresh_graph
from agent.nodes.curator import make_curator_node
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.metrics import make_update_metrics_node
from agent.state import ExtractionResult
from agent.subgraph import build_extraction_subgraph
from tests.agent.conftest import FakeModelFactory, FakeScraper, FakeStructuredModel

GOOD = {
    "status": "OPEN",
    "hours_notes": "x",
    "hours_today": "x",
    "eligibility_rules": ["Open to all"],
    "is_id_required": False,
    "residency_req": None,
    "special_notes": None,
    "confidence": 8,
}


async def test_checkpointer_persists_and_retrieves_state(test_db):
    """Run the refresh graph with a real MongoDB checkpointer.

    Steps:
    1. Seed one stale pantry so the run actually processes a source.
    2. Build the graph with the checkpointer attached (db_name=equitable_test).
    3. ainvoke — assert the run succeeded.
    4. aget_state with the same thread_id — assert the checkpointed state is
       retrievable and contains a successful result (the resume contract).
    """
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    await test_db["pantries"].insert_one(
        {
            "name": "p",
            "address": "a",
            "lat": 1,
            "lng": 2,
            "hours_notes": "OLD",
            "status": "UNKNOWN",
            "source_url": "https://p.org",
            "last_updated": old,
        }
    )

    factory = FakeModelFactory(
        [FakeStructuredModel(scripted=[ExtractionResult(**GOOD)])]
    )
    tracker = CostTracker(1.0)
    sub = build_extraction_subgraph(
        FakeScraper(), factory, tracker, lambda: "SYS", db=test_db
    )

    # thread_id is the "run_id" that identifies this run in the checkpoint store.
    thread_id = "resume-test-001"
    cfg = {"configurable": {"thread_id": thread_id}}

    async with mongo_checkpointer(
        uri=os.getenv("MONGO_URI"), db_name="equitable_test"
    ) as cp:
        app = build_refresh_graph(
            make_load_sources_node(db=test_db),
            make_curator_node(ranker=None),
            sub,
            tracker,
            make_update_metrics_node(db=test_db),
            checkpointer=cp,
        )

        # --- First (and only) invocation ---
        final = await app.ainvoke(
            {"run_id": thread_id, "cost_budget_usd": 1.0}, cfg
        )
        assert final["results"], "Graph produced no results"
        assert final["results"][0]["outcome"] == "success", (
            f"Expected 'success', got {final['results'][0]['outcome']!r}"
        )

        # --- Resume contract: state is retrievable under the same thread_id ---
        # aget_state reads back the checkpointed final state from MongoDB.
        # If the checkpoint was NOT persisted this would return an empty snapshot.
        state = await app.aget_state(cfg)
        assert state.values, "aget_state returned empty values — checkpoint not persisted"
        assert state.values["results"][0]["outcome"] == "success", (
            "Checkpointed state does not reflect a successful run"
        )
