# backend_ml/services/firecrawl_fetcher.py
"""OPTIONAL paid fallback. Disabled unless FIRECRAWL_FALLBACK_ENABLED=true.

A persistent monthly counter (Mongo `scraper_usage`) guarantees the number of
Firecrawl pages never exceeds FIRECRAWL_MONTHLY_BUDGET — so it never bills
beyond the configured (free-tier-sized) allotment.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("equitable")


def _import_async_firecrawl():
    from firecrawl import AsyncFirecrawl
    return AsyncFirecrawl


class FirecrawlFetcher:
    name = "firecrawl"

    def __init__(self, api_key, monthly_budget, db_getter, enabled: bool = True):
        self._api_key = api_key
        self._monthly_budget = monthly_budget
        self._db_getter = db_getter
        self.enabled = enabled

    @classmethod
    def from_env(cls):
        key = os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_KEY")
        budget = int(os.getenv("FIRECRAWL_MONTHLY_BUDGET", "400"))
        from database import get_database
        return cls(api_key=key, monthly_budget=budget, db_getter=get_database, enabled=True)

    def _month_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    async def _used_this_month(self) -> int:
        doc = await self._db_getter()["scraper_usage"].find_one(
            {"_id": f"firecrawl:{self._month_key()}"})
        return (doc or {}).get("count", 0)

    async def fetch(self, url: str) -> Optional[str]:
        if not self._api_key:
            return None
        if await self._used_this_month() >= self._monthly_budget:
            logger.warning("Firecrawl monthly budget exhausted — skipping (no charge)",
                           extra={"event": "firecrawl_budget_exhausted",
                                  "budget": self._monthly_budget})
            return None
        try:
            AsyncFirecrawl = _import_async_firecrawl()
            fc = AsyncFirecrawl(api_key=self._api_key)
            res = await fc.scrape(url, formats=["markdown"])
            md = getattr(res, "markdown", None)
            if md and md.strip():
                await self._db_getter()["scraper_usage"].update_one(
                    {"_id": f"firecrawl:{self._month_key()}"},
                    {"$inc": {"count": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
                    upsert=True,
                )
                return md
            return None
        except Exception as e:
            logger.warning("Firecrawl fetch failed",
                           extra={"event": "firecrawl_failed", "url": url, "error": str(e)})
            return None
