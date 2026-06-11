# backend_ml/agent/nodes/aggregate.py
"""Aggregate node — build a run summary from per-source results."""

import logging

from agent.state import ParentState

logger = logging.getLogger("equitable")


async def aggregate_report_node(state: ParentState) -> dict:
    """Summarise the run outcomes and log a structured event.

    Returns ``{"results": results}`` as a passthrough so downstream nodes
    (update_metrics) still see the full results list.  The summary itself is
    captured via structured logging rather than stored in state, keeping
    ParentState lean.
    """
    results = state.get("results", [])
    summary = {
        "selected": len(state.get("selected_sources", [])),
        "processed": len(results),
        "succeeded": sum(1 for r in results if r["outcome"] == "success"),
        "failed": sum(1 for r in results if r["outcome"] == "failed"),
        "skipped_budget": sum(1 for r in results if r["outcome"] == "skipped_budget"),
        "cost_spent_usd": round(state.get("cost_spent_usd", 0.0), 4),
        "quarantined": len(state.get("quarantined", [])),
    }
    quarantined = state.get("quarantined", [])
    logger.info(
        "Refresh run summary",
        extra={
            "event": "refresh_summary",
            **summary,
            "curator_reasoning": state.get("curator_reasoning", ""),
            "quarantined_sources": [q.get("source_url") for q in quarantined],
        },
    )
    return {"results": results}  # passthrough; summary is logged
