"""Scrape node — wraps ScraperService with provenance."""

import time
from agent.state import ExtractionState


def make_scrape_node(scraper):
    async def scrape_node(state: ExtractionState) -> dict:
        start = time.time()
        result = await scraper.scrape_with_provenance(state["source_url"])
        latency_ms = round((time.time() - start) * 1000, 2)
        if not result.content:
            return {"raw_markdown": None, "latency_ms": latency_ms, "outcome": "failed"}
        return {"raw_markdown": result.content, "scrape_method": result.method,
                "latency_ms": latency_ms}
    return scrape_node
