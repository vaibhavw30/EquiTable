"""Scrape node — wraps ScraperService (services/scraper.py)."""

import logging
import time
from agent.state import ExtractionState

logger = logging.getLogger("equitable")


def make_scrape_node(scraper):
    async def scrape_node(state: ExtractionState) -> dict:
        start = time.time()
        markdown = await scraper.scrape_url(state["source_url"])
        latency_ms = round((time.time() - start) * 1000, 2)
        if not markdown:
            logger.warning(
                "Agent scrape failed",
                extra={"event": "agent_scrape_failed", "source_url": state.get("source_url")},
            )
            return {"raw_markdown": None, "latency_ms": latency_ms, "outcome": "failed"}
        return {"raw_markdown": markdown, "latency_ms": latency_ms}
    return scrape_node
