# backend_ml/agent/graph.py
"""Assemble the parent refresh graph:

    load_sources → curator → process_sources → aggregate_report → update_metrics → END

``make_process_sources_node`` fans out over ``selected_sources`` under an
asyncio semaphore (bounded by MAX_CONCURRENT), gated by the cost budget.

Robustness: each per-source invocation is wrapped in try/except so a single
failing source cannot crash the whole asyncio.gather.  Exceptions are logged
as structured events and the source is recorded with outcome="failed".
"""

import asyncio
import logging

from langgraph.graph import StateGraph, START, END

from agent.config import MAX_CONCURRENT
from agent.state import ParentState
from agent.nodes.aggregate import aggregate_report_node

logger = logging.getLogger("equitable")


def make_process_sources_node(subgraph, cost_tracker):
    """Fan out over selected sources under a semaphore, gated by the budget.

    Args:
        subgraph: Compiled LangGraph subgraph (or duck-typed fake with ainvoke).
        cost_tracker: CostTracker — checked before each invocation; exhausted →
            source recorded as "skipped_budget" without calling the subgraph.
    """
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def _run_one(src: dict) -> dict:
        async with sem:
            if cost_tracker.is_exhausted:
                return {
                    "source_url": src["source_url"],
                    "outcome": "skipped_budget",
                    "latency_ms": 0.0,
                    "model_tier": None,
                    "had_validation_error": False,
                }
            try:
                final = await subgraph.ainvoke({
                    "source_url": src["source_url"],
                    "pantry_id": src.get("pantry_id", ""),
                    "model_tier": 0,
                    "retry_count": 0,
                    "validation_errors": [],
                })
                return {
                    "source_url": src["source_url"],
                    "outcome": final.get("outcome", "failed"),
                    "latency_ms": final.get("latency_ms", 0.0),
                    "model_tier": final.get("model_tier", 0),
                    "had_validation_error": bool(final.get("validation_errors")),
                }
            except Exception as exc:
                # Defense-in-depth: one bad source must not abort the batch.
                logger.error(
                    "Unhandled exception in per-source subgraph invocation",
                    extra={
                        "event": "agent_source_error",
                        "source_url": src["source_url"],
                        "error": str(exc),
                    },
                    exc_info=True,
                )
                return {
                    "source_url": src["source_url"],
                    "outcome": "failed",
                    "latency_ms": 0.0,
                    "model_tier": None,
                    "had_validation_error": False,
                }

    async def process_sources_node(state: ParentState) -> dict:
        selected = state.get("selected_sources", [])
        results = await asyncio.gather(*[_run_one(s) for s in selected])
        return {
            "results": list(results),
            "cost_spent_usd": cost_tracker.spent_usd,
        }

    return process_sources_node


def build_refresh_graph(
    load_node,
    curator_node,
    subgraph,
    cost_tracker,
    update_metrics_node,
    checkpointer=None,
):
    """Assemble and compile the top-level refresh graph.

    Topology:
        START → load_sources → curator → process_sources
              → aggregate_report → update_metrics → END

    Args:
        load_node: Async node produced by make_load_sources_node().
        curator_node: Async node produced by make_curator_node().
        subgraph: Compiled extraction subgraph (or duck-typed fake).
        cost_tracker: CostTracker used by process_sources_node.
        update_metrics_node: Async node produced by make_update_metrics_node().
        checkpointer: Optional LangGraph checkpointer (e.g. AsyncMongoDBSaver).
    """
    g = StateGraph(ParentState)

    g.add_node("load_sources", load_node)
    g.add_node("curator", curator_node)
    g.add_node("process_sources", make_process_sources_node(subgraph, cost_tracker))
    g.add_node("aggregate_report", aggregate_report_node)
    g.add_node("update_metrics", update_metrics_node)

    g.add_edge(START, "load_sources")
    g.add_edge("load_sources", "curator")
    g.add_edge("curator", "process_sources")
    g.add_edge("process_sources", "aggregate_report")
    g.add_edge("aggregate_report", "update_metrics")
    g.add_edge("update_metrics", END)

    return g.compile(checkpointer=checkpointer)
