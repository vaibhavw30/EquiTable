# backend_ml/agent/nodes/metrics.py
"""Update node — write per-source metrics after a run.

One atomic upsert per processed source. Running averages and rates are
recomputed from the post-increment totals.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from agent.config import model_for_tier
from agent.state import ParentState

logger = logging.getLogger("equitable")


def make_update_metrics_node(db=None):
    def _collection():
        if db is not None:
            return db["source_metrics"]
        from database import get_collection
        return get_collection("source_metrics")

    async def update_metrics_node(state: ParentState) -> dict:
        col = _collection()
        now = datetime.now(timezone.utc)
        # `results` has at most one entry per source_url per run (see ParentState.results),
        # so the read-then-write upsert below is race-free.
        for r in state.get("results", []):
            if r.get("outcome") == "skipped_budget":
                continue   # never attempted; don't record as a run

            url = r["source_url"]
            success = r["outcome"] == "success"
            existing = await col.find_one({"source_url": url}) or {}

            total_runs = existing.get("total_runs", 0) + 1
            successes = existing.get("successes", 0) + (1 if success else 0)
            failures = existing.get("failures", 0) + (0 if success else 1)
            val_errors = existing.get("validation_error_count", 0) + (
                1 if r.get("had_validation_error") else 0)
            prev_avg = existing.get("avg_latency_ms", 0.0)
            prev_n = existing.get("total_runs", 0)
            avg_latency = (prev_avg * prev_n + r.get("latency_ms", 0.0)) / total_runs
            consecutive = 0 if success else existing.get("consecutive_failures", 0) + 1

            doc = {
                "source_url": url,
                "domain": urlparse(url).netloc,
                "total_runs": total_runs,
                "successes": successes,
                "failures": failures,
                "validation_error_count": val_errors,
                "success_rate": successes / total_runs,
                "validation_error_rate": val_errors / total_runs,
                "avg_latency_ms": round(avg_latency, 2),
                "consecutive_failures": consecutive,
                "last_scraped": now,
                "last_model_used": model_for_tier(r.get("model_tier") or 0),
            }
            if success:
                doc["last_success"] = now
            else:
                doc["last_error"] = r.get("reason", "unknown")

            await col.update_one({"source_url": url}, {"$set": doc}, upsert=True)
            logger.info(
                "Agent metrics updated",
                extra={"event": "agent_metrics_updated", "source_url": url,
                       "success": success, "total_runs": total_runs},
            )
        return {}
    return update_metrics_node
