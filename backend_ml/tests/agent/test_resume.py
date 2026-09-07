# backend_ml/tests/agent/test_resume.py
"""Resume-on-crash tests for the refresh entrypoint.

`tests/agent/test_checkpointer.py` proves the MongoDB saver is *durable* —
state written in one connection is readable from another. That is necessary
but not sufficient: durability is worthless if the entrypoint never reads the
checkpoint back.

Before this, `agent/cli.py` generated `run_id = uuid4()` on every process
start and used it as the thread_id, so a restarted container always opened a
fresh checkpoint namespace and redid the entire run. These tests cover the two
pieces that close that gap:

  1. `resolve_run_id()` — the thread_id is stable across restarts.
  2. `invoke_or_resume()` — an existing checkpoint is resumed, not restarted,
     and work already completed is not repeated.
"""

import os
from datetime import datetime, timezone, timedelta

import pytest

from agent.checkpointer import mongo_checkpointer
from agent.cli import RUN_ID_ENV_VAR, invoke_or_resume, resolve_run_id
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


class TestResolveRunId:
    """The thread_id must be stable across restarts of the same scheduled run."""

    def test_uses_injected_env_var(self, monkeypatch):
        """A Kubernetes Job name injected via the downward API wins."""
        monkeypatch.setenv(RUN_ID_ENV_VAR, "equitable-refresh-29385360")
        assert resolve_run_id() == "equitable-refresh-29385360"

    def test_injected_value_is_stable_across_calls(self, monkeypatch):
        """Two processes in the same Job resolve to the SAME id.

        This is the property that makes resume possible at all: the restarted
        pod must land on the thread the dead pod was checkpointing into.
        """
        monkeypatch.setenv(RUN_ID_ENV_VAR, "equitable-refresh-29385360")
        assert resolve_run_id() == resolve_run_id()

    def test_falls_back_to_uuid_when_unset(self, monkeypatch):
        """Ad-hoc local runs keep the old behavior: each run stands alone."""
        monkeypatch.delenv(RUN_ID_ENV_VAR, raising=False)
        first, second = resolve_run_id(), resolve_run_id()
        assert first != second
        assert len(first) == 36  # uuid4 string form

    def test_blank_env_var_falls_back_to_uuid(self, monkeypatch):
        """An empty/whitespace value must not become the thread_id.

        An empty string is falsy but a *valid* dict key, so passing it through
        would silently collapse every run onto one shared thread.
        """
        monkeypatch.setenv(RUN_ID_ENV_VAR, "   ")
        assert len(resolve_run_id()) == 36


class _FakeSnapshot:
    def __init__(self, values, next_nodes=()):
        self.values = values
        self.next = next_nodes


class _RecordingApp:
    """Records how ainvoke was called so the resume decision is observable."""

    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.invoked_with = []

    async def aget_state(self, config):
        return self._snapshot

    async def ainvoke(self, payload, config):
        self.invoked_with.append(payload)
        return {"results": []}


@pytest.mark.asyncio
class TestInvokeOrResume:
    async def test_starts_fresh_when_no_checkpoint(self):
        """An empty snapshot means a new run: pass the initial state."""
        app = _RecordingApp(_FakeSnapshot(values={}))
        initial = {"run_id": "r1", "cost_budget_usd": 0.5}

        await invoke_or_resume(app, {"configurable": {"thread_id": "r1"}}, initial)

        assert app.invoked_with == [initial]

    async def test_resumes_when_checkpoint_exists(self):
        """A populated snapshot means resume: pass None, never the initial state.

        Passing the initial state here would reset the run to START and redo
        every source — the exact bug this guards.
        """
        app = _RecordingApp(
            _FakeSnapshot(values={"results": [{"outcome": "success"}]},
                         next_nodes=("update_metrics",))
        )

        await invoke_or_resume(
            app,
            {"configurable": {"thread_id": "r1"}},
            {"run_id": "r1", "cost_budget_usd": 0.5},
        )

        assert app.invoked_with == [None], (
            "resume must invoke with None; passing initial state restarts the run"
        )


@pytest.mark.asyncio
class TestCrashAndResumeEndToEnd:
    async def test_crashed_run_resumes_without_redoing_work(self, test_db):
        """Kill a run mid-graph, restart on the same thread, assert no re-work.

        Simulates the pod-killed-mid-crawl case:

          run 1 — load_sources → curator → process_sources → aggregate_report
                  → update_metrics RAISES (the "crash")
          run 2 — same thread_id, resumed via invoke_or_resume

        The assertion that matters is `load_calls == 1`: the resumed run picks
        up after the last completed node instead of re-entering at START and
        re-scraping everything. A fresh uuid4 thread_id would make this 2.
        """
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        await test_db["pantries"].insert_one(
            {
                "name": "resume-p", "address": "a", "lat": 1, "lng": 2,
                "hours_notes": "OLD", "status": "UNKNOWN",
                "source_url": "https://resume-p.org", "last_updated": old,
            }
        )

        load_calls = {"n": 0}
        real_load = make_load_sources_node(db=test_db)

        async def counting_load(state):
            load_calls["n"] += 1
            return await real_load(state)

        metrics_calls = {"n": 0}
        real_metrics = make_update_metrics_node(db=test_db)

        async def crash_once_metrics(state):
            metrics_calls["n"] += 1
            if metrics_calls["n"] == 1:
                raise RuntimeError("simulated pod kill (SIGKILL mid-run)")
            return await real_metrics(state)

        def build(cp):
            factory = FakeModelFactory(
                [FakeStructuredModel(scripted=[ExtractionResult(**GOOD)])]
            )
            tracker = CostTracker(1.0)
            sub = build_extraction_subgraph(
                FakeScraper(), factory, tracker, lambda: "SYS", db=test_db
            )
            return build_refresh_graph(
                counting_load,
                make_curator_node(ranker=None),
                sub,
                tracker,
                crash_once_metrics,
                checkpointer=cp,
            )

        thread_id = "equitable-refresh-crashtest"
        cfg = {"configurable": {"thread_id": thread_id}}
        initial = {"run_id": thread_id, "cost_budget_usd": 1.0}

        # --- Run 1: crashes in update_metrics ---
        async with mongo_checkpointer(
            uri=os.getenv("MONGO_URI"), db_name="equitable_test"
        ) as cp:
            app = build(cp)
            with pytest.raises(RuntimeError, match="simulated pod kill"):
                await invoke_or_resume(app, cfg, initial)

        assert load_calls["n"] == 1, "sanity: first run should load sources once"

        # --- Run 2: fresh process, fresh connection, SAME thread_id ---
        async with mongo_checkpointer(
            uri=os.getenv("MONGO_URI"), db_name="equitable_test"
        ) as cp2:
            app2 = build(cp2)
            final = await invoke_or_resume(app2, cfg, initial)

        assert load_calls["n"] == 1, (
            f"resumed run re-executed load_sources ({load_calls['n']} calls) — "
            "it restarted from START instead of resuming from the checkpoint"
        )
        assert metrics_calls["n"] == 2, "update_metrics should have been retried"
        assert final["results"], "resumed run produced no results"
        assert final["results"][0]["outcome"] == "success"

    async def test_completed_run_is_not_redone(self, test_db):
        """Re-invoking a finished thread returns its state without re-work.

        This is what makes a duplicate Job pod harmless: the second pod finds a
        completed checkpoint and does nothing rather than double-scraping.
        """
        old = datetime.now(timezone.utc) - timedelta(hours=48)
        await test_db["pantries"].insert_one(
            {
                "name": "done-p", "address": "a", "lat": 5, "lng": 6,
                "hours_notes": "OLD", "status": "UNKNOWN",
                "source_url": "https://done-p.org", "last_updated": old,
            }
        )

        load_calls = {"n": 0}
        real_load = make_load_sources_node(db=test_db)

        async def counting_load(state):
            load_calls["n"] += 1
            return await real_load(state)

        def build(cp):
            factory = FakeModelFactory(
                [FakeStructuredModel(scripted=[ExtractionResult(**GOOD)])]
            )
            tracker = CostTracker(1.0)
            sub = build_extraction_subgraph(
                FakeScraper(), factory, tracker, lambda: "SYS", db=test_db
            )
            return build_refresh_graph(
                counting_load,
                make_curator_node(ranker=None),
                sub,
                tracker,
                make_update_metrics_node(db=test_db),
                checkpointer=cp,
            )

        thread_id = "equitable-refresh-completed"
        cfg = {"configurable": {"thread_id": thread_id}}
        initial = {"run_id": thread_id, "cost_budget_usd": 1.0}

        async with mongo_checkpointer(
            uri=os.getenv("MONGO_URI"), db_name="equitable_test"
        ) as cp:
            first = await invoke_or_resume(build(cp), cfg, initial)
        assert first["results"], "first run produced no results"
        assert load_calls["n"] == 1

        async with mongo_checkpointer(
            uri=os.getenv("MONGO_URI"), db_name="equitable_test"
        ) as cp2:
            second = await invoke_or_resume(build(cp2), cfg, initial)

        assert load_calls["n"] == 1, (
            "re-invoking a completed thread re-ran the graph — a duplicate pod "
            "would double-scrape every source"
        )
        assert second["results"] == first["results"]
