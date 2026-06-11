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

    An entry that is an Exception instance simulates a parse failure — ainvoke
    returns {"raw": ..., "parsed": None, "parsing_error": <exc>}, matching the
    real with_structured_output(include_raw=True) behaviour on bad output.
    """
    def __init__(self, scripted):
        if not scripted:
            raise ValueError("FakeStructuredModel requires a non-empty scripted list")
        self._scripted = list(scripted)
        self.calls = 0
        self.last_messages = None

    async def ainvoke(self, messages):
        self.last_messages = messages
        result = self._scripted[min(self.calls, len(self._scripted) - 1)]
        self.calls += 1
        if isinstance(result, Exception):
            return {"raw": FakeRawMessage(), "parsed": None, "parsing_error": result}
        if isinstance(result, dict):
            result = ExtractionResult(**result)
        return {"raw": FakeRawMessage(), "parsed": result, "parsing_error": None}


class FakeModelFactory:
    """Returns a FakeStructuredModel per tier; records which tiers were used."""
    def __init__(self, scripted_by_tier):
        if not scripted_by_tier:
            raise ValueError("FakeModelFactory requires a non-empty scripted_by_tier list")
        self._by_tier = scripted_by_tier
        self.tiers_used = []

    def get(self, tier):
        self.tiers_used.append(tier)
        idx = min(tier, len(self._by_tier) - 1)
        return self._by_tier[idx]

    def name_for_tier(self, tier):
        from agent.config import model_for_tier
        return model_for_tier(tier)


class FakeScraper:
    """Mimics ScraperService.scrape_url."""
    def __init__(self, markdown="# Pantry\nMon-Fri 9am-5pm. No ID required."):
        self._markdown = markdown

    async def scrape_url(self, url):
        return self._markdown
