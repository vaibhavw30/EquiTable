# backend_ml/tests/test_fallback_fetcher.py
import httpx
import pytest

from services.fallback_fetcher import JinaReaderFetcher, build_default_fallback_chain, _bool_env


class _FakeResponse:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text
    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=None)


class _FakeClient:
    """Stands in for httpx.AsyncClient; returns scripted responses in order."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def get(self, url, headers=None):
        self.calls.append(url)
        return self._responses[min(len(self.calls) - 1, len(self._responses) - 1)]


async def test_jina_returns_text_on_200(monkeypatch):
    fake = _FakeClient([_FakeResponse(200, "Markdown Content: real pantry hours")])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: fake)
    out = await JinaReaderFetcher().fetch("https://x.org")
    assert "real pantry hours" in out
    assert fake.calls == ["https://r.jina.ai/https://x.org"]


async def test_jina_empty_body_returns_none(monkeypatch):
    fake = _FakeClient([_FakeResponse(200, "   \n  ")])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: fake)
    assert await JinaReaderFetcher().fetch("https://x.org") is None


async def test_jina_retries_on_429_then_succeeds(monkeypatch):
    fake = _FakeClient([_FakeResponse(429), _FakeResponse(200, "content here")])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: fake)
    async def _no_sleep(*a, **k): return None
    monkeypatch.setattr("services.fallback_fetcher.asyncio.sleep", _no_sleep)
    out = await JinaReaderFetcher(max_retries=3).fetch("https://x.org")
    assert out == "content here"
    assert len(fake.calls) == 2


async def test_jina_all_429_returns_none(monkeypatch):
    fake = _FakeClient([_FakeResponse(429)])
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: fake)
    async def _no_sleep(*a, **k): return None
    monkeypatch.setattr("services.fallback_fetcher.asyncio.sleep", _no_sleep)
    assert await JinaReaderFetcher(max_retries=2).fetch("https://x.org") is None


def test_default_chain_is_jina_only(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_FALLBACK_ENABLED", raising=False)
    monkeypatch.setenv("JINA_ENABLED", "true")
    chain = build_default_fallback_chain()
    assert [f.name for f in chain] == ["jina"]


def test_jina_can_be_disabled(monkeypatch):
    monkeypatch.setenv("JINA_ENABLED", "false")
    monkeypatch.delenv("FIRECRAWL_FALLBACK_ENABLED", raising=False)
    assert build_default_fallback_chain() == []


def test_bool_env_parsing(monkeypatch):
    monkeypatch.setenv("X", "YES")
    assert _bool_env("X", False) is True
    monkeypatch.setenv("X", "0")
    assert _bool_env("X", True) is False
    monkeypatch.delenv("X", raising=False)
    assert _bool_env("X", True) is True
