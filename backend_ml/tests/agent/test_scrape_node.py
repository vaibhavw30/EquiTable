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
