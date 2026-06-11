"""Persist node — update an existing pantry's dynamic fields after a refresh.

Identity fields (name/address/lat/lng/city/state) are preserved; only the
LLM-extracted dynamic fields + freshness metadata are written. If the final
attempt is still invalid (validation_errors non-empty), we DO NOT write —
refusing to clobber good existing data with a bad extraction.
"""

import logging
from datetime import datetime, timezone
from agent.state import ExtractionState

logger = logging.getLogger("equitable")


def make_persist_node(db=None):
    def _collection():
        if db is not None:
            return db["pantries"]
        from database import get_collection
        return get_collection("pantries")

    async def persist_node(state: ExtractionState) -> dict:
        if state.get("validation_errors"):
            logger.info(
                "Agent persist skipped (still invalid after retries)",
                extra={"event": "agent_persist_skipped", "source_url": state.get("source_url")},
            )
            return {"outcome": "failed", "final_update": None}

        data = state.get("extracted_data")
        if not data:
            return {"outcome": "failed", "final_update": None}

        update = {
            "status": data["status"],
            "hours_notes": data["hours_notes"],
            "hours_today": data["hours_today"],
            "eligibility_rules": data["eligibility_rules"],
            "is_id_required": data["is_id_required"],
            "residency_req": data.get("residency_req"),
            "special_notes": data.get("special_notes"),
            "confidence": data["confidence"],
            "last_updated": datetime.now(timezone.utc),
            "scraped_at": datetime.now(timezone.utc),
            "scrape_method": state.get("scrape_method", "crawl4ai"),
        }
        await _collection().update_one(
            {"source_url": state["source_url"]}, {"$set": update}
        )
        return {"outcome": "success", "final_update": update}
    return persist_node
