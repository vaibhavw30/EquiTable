# backend_ml/agent/nodes/load_sources.py
"""Load node — find stale pantries with a source_url and join their metrics."""

from datetime import datetime, timezone, timedelta
from agent.config import FRESHNESS_FLOOR_HOURS
from agent.state import ParentState


def make_load_sources_node(db=None):
    def _db():
        if db is not None:
            return db
        from database import get_database
        return get_database()

    async def load_sources_node(state: ParentState) -> dict:
        database = _db()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_FLOOR_HOURS)

        candidates = []
        cursor = database["pantries"].find({
            "source_url": {"$exists": True, "$nin": [None, ""]},
            "last_updated": {"$lt": cutoff},
        })
        async for doc in cursor:
            candidates.append({
                "pantry_id": str(doc["_id"]),
                "source_url": doc["source_url"],
                "name": doc.get("name"),
                "city": doc.get("city"),
                "state": doc.get("state"),
                "last_updated": doc.get("last_updated"),
            })

        # Join metrics
        metrics = {}
        async for m in database["source_metrics"].find({}):
            metrics[m["source_url"]] = m
        for c in candidates:
            m = metrics.get(c["source_url"], {})
            c["consecutive_failures"] = m.get("consecutive_failures", 0)
            c["success_rate"] = m.get("success_rate", None)
            c["avg_latency_ms"] = m.get("avg_latency_ms", None)

        return {"candidate_sources": candidates}
    return load_sources_node
