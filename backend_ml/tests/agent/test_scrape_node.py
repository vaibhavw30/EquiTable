# backend_ml/tests/agent/test_scrape_node.py
import time
from agent.nodes.scrape import make_scrape_node
from tests.agent.conftest import FakeScraper


async def test_scrape_node_populates_markdown_and_latency():
    node = make_scrape_node(FakeScraper(markdown="# Food Pantry\nOpen Mondays"))
    out = await node({"source_url": "https://x.org", "model_tier": 0, "retry_count": 0})
    assert "Food Pantry" in out["raw_markdown"]
    assert out["latency_ms"] >= 0


async def test_scrape_node_empty_marks_failed():
    node = make_scrape_node(FakeScraper(markdown=None))
    out = await node({"source_url": "https://x.org"})
    assert out["raw_markdown"] is None
    assert out["outcome"] == "failed"


from services.scraper import ScrapeResult


class _ProvScraper:
    def __init__(self, result): self._result = result
    async def scrape_with_provenance(self, url): return self._result


async def test_scrape_node_threads_method():
    node = make_scrape_node(_ProvScraper(ScrapeResult("# Pantry\nhours", "jina")))
    out = await node({"source_url": "https://x.org"})
    assert out["raw_markdown"] == "# Pantry\nhours"
    assert out["scrape_method"] == "jina"


async def test_scrape_node_none_marks_failed():
    node = make_scrape_node(_ProvScraper(ScrapeResult(None, "none")))
    out = await node({"source_url": "https://x.org"})
    assert out["raw_markdown"] is None and out["outcome"] == "failed"
