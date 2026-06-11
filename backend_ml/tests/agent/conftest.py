# backend_ml/tests/agent/conftest.py
"""Fakes for agent node/subgraph tests — no network, deterministic."""

from agent.state import ExtractionResult


class FakeRawMessage:
    """Stands in for a LangChain AIMessage carrying usage_metadata."""
    def __init__(self, input_tokens=100, output_tokens=50):
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }


class FakeStructuredModel:
    """Mimics ChatGoogleGenerativeAI.with_structured_output(..., include_raw=True).

    `scripted` is a list of ExtractionResult (or dict) returned in order per
    ainvoke call, letting a test simulate 'fail then succeed' retries.
    """
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = 0

    async def ainvoke(self, messages):
        result = self._scripted[min(self.calls, len(self._scripted) - 1)]
        self.calls += 1
        if isinstance(result, dict):
            result = ExtractionResult(**result)
        return {"raw": FakeRawMessage(), "parsed": result, "parsing_error": None}


class FakeModelFactory:
    """Returns a FakeStructuredModel per tier; records which tiers were used."""
    def __init__(self, scripted_by_tier):
        self._by_tier = scripted_by_tier
        self.tiers_used = []

    def get(self, tier):
        self.tiers_used.append(tier)
        idx = min(tier, len(self._by_tier) - 1)
        return self._by_tier[idx]


class FakeScraper:
    """Mimics ScraperService.scrape_url."""
    def __init__(self, markdown="# Pantry\nMon-Fri 9am-5pm. No ID required."):
        self._markdown = markdown

    async def scrape_url(self, url):
        return self._markdown
