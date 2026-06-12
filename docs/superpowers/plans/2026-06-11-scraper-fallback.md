# Free-First Scraper Fallback — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pluggable, free-first fallback chain to `ScraperService` so JS/anti-bot pantry sites (which Crawl4AI 0.8.9 returns empty for) are recovered via the free Jina Reader, with per-source provenance and an optional, hard-capped, off-by-default Firecrawl tier.

**Architecture:** Keep Crawl4AI as the free primary. When it yields `< MIN_CONTENT_CHARS` (200), try an ordered chain of `FallbackFetcher`s — default `[JinaReaderFetcher]` (free `r.jina.ai`). The public `scrape_url(url) -> Optional[str]` interface is preserved; a new `scrape_with_provenance(url) -> ScrapeResult` returns `(content, method)` so the agent records which tool won. Firecrawl is a separate fetcher, disabled by default and capped by a persistent monthly counter so it can never bill.

**Tech Stack:** Python 3.10+ async, httpx (Jina), Crawl4AI (existing), firecrawl-py 4.x (optional), Motor/MongoDB, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-11-scraper-fallback-design.md`

**Conventions used throughout:**
- Run from `backend_ml/` with the worktree venv: `./venv/bin/python`. `pytest.ini` sets `asyncio_mode = auto` (no `@pytest.mark.asyncio` needed).
- Offline tests (fetchers, scraper) need no DB. Agent/persist tests use the existing `test_db` fixture (local Mongo / Atlas via `MONGO_URI`).
- Commit after each task with explicit `git add <paths>` (never `git add -A`).
- Shell variables do not persist between steps.

**Execution prerequisites (controller sets up before dispatch):** worktree venv with `requirements.txt` installed; local Mongo reachable via `MONGO_URI`; `.env` present. `JINA_API_KEY` (optional) and `RUN_LIVE_SCRAPE=1` only needed for the Task 7 live smoke.

---

## File Structure

**Created:**
- `backend_ml/services/fallback_fetcher.py` — `FallbackFetcher` protocol, `JinaReaderFetcher`, `build_default_fallback_chain`, `_bool_env`
- `backend_ml/services/firecrawl_fetcher.py` — optional capped `FirecrawlFetcher` (off by default)
- `backend_ml/tests/test_fallback_fetcher.py`
- `backend_ml/tests/test_firecrawl_fetcher.py`
- `backend_ml/tests/test_fallback_live.py` — opt-in live smoke

**Modified:**
- `backend_ml/services/scraper.py` — `ScrapeResult`, `MIN_CONTENT_CHARS`, `_crawl4ai_scrape` (renamed body), `scrape_with_provenance`, `scrape_url` wrapper, injectable chain
- `backend_ml/agent/state.py` — add `scrape_method` to `ExtractionState`
- `backend_ml/agent/nodes/scrape.py` — use `scrape_with_provenance`, thread `scrape_method`
- `backend_ml/agent/nodes/persist.py` — record real `scrape_method`
- `backend_ml/tests/test_scraper.py` — extend for the chain
- `backend_ml/tests/agent/test_scrape_node.py` — provenance
- `backend_ml/tests/agent/test_persist_node.py` — provenance write
- `backend_ml/requirements.txt` — `firecrawl-py>=4.0`
- `docs/decisions.md` — ADR-021 + ADR-008 status note

---

## Task 1: `FallbackFetcher` protocol + `JinaReaderFetcher`

**Files:**
- Create: `backend_ml/services/fallback_fetcher.py`
- Test: `backend_ml/tests/test_fallback_fetcher.py`

- [ ] **Step 1: Write the failing test.**

```python
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
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/test_fallback_fetcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.fallback_fetcher'`.

- [ ] **Step 3: Write `fallback_fetcher.py`.**

```python
# backend_ml/services/fallback_fetcher.py
"""Fallback content fetchers used when Crawl4AI returns insufficient content.

Each fetcher implements `async fetch(url) -> Optional[str]` returning clean
markdown, or None on failure. Fetchers are tried in order by ScraperService.
Budget/cost enforcement (if any) lives INSIDE fetch(): a fetcher over budget
returns None without making a billable call.
"""

import asyncio
import logging
import os
from typing import Optional, Protocol, runtime_checkable

import httpx

logger = logging.getLogger("equitable")


@runtime_checkable
class FallbackFetcher(Protocol):
    name: str
    enabled: bool
    async def fetch(self, url: str) -> Optional[str]: ...


class JinaReaderFetcher:
    """Free JS-rendering reader via https://r.jina.ai/{url}.

    No API key required (IP-rate-limited). An optional free JINA_API_KEY raises
    the limit. Returns markdown text. Retries with backoff on HTTP 429.
    """
    name = "jina"

    def __init__(self, api_key: Optional[str] = None, timeout: float = 45.0,
                 max_retries: int = 3, enabled: bool = True):
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries
        self.enabled = enabled

    async def fetch(self, url: str) -> Optional[str]:
        endpoint = f"https://r.jina.ai/{url}"
        headers = {"X-Return-Format": "markdown"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        backoff = 2.0
        for attempt in range(1, self._max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(endpoint, headers=headers)
                if resp.status_code == 429:
                    logger.warning("Jina rate-limited",
                                   extra={"event": "jina_429", "url": url, "attempt": attempt})
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                resp.raise_for_status()
                text = resp.text or ""
                return text if text.strip() else None
            except Exception as e:
                logger.warning("Jina fetch failed",
                               extra={"event": "jina_failed", "url": url,
                                      "attempt": attempt, "error": str(e)})
                if attempt < self._max_retries:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        return None


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def build_default_fallback_chain() -> list:
    """Construct the fallback chain from environment. Default = [Jina] (free)."""
    chain: list = []
    if _bool_env("JINA_ENABLED", True):
        chain.append(JinaReaderFetcher(api_key=os.getenv("JINA_API_KEY"), enabled=True))
    if _bool_env("FIRECRAWL_FALLBACK_ENABLED", False):  # OFF by default → $0
        from services.firecrawl_fetcher import FirecrawlFetcher
        chain.append(FirecrawlFetcher.from_env())
    return chain
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/test_fallback_fetcher.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/services/fallback_fetcher.py backend_ml/tests/test_fallback_fetcher.py
git commit -m "feat(scraper): add FallbackFetcher protocol + free JinaReaderFetcher"
```

---

## Task 2: `ScraperService` provenance + fallback chain

**Files:**
- Modify: `backend_ml/services/scraper.py`
- Test: `backend_ml/tests/test_scraper.py` (extend)

- [ ] **Step 1: Write the failing test** (append to `test_scraper.py`). These monkeypatch the private Crawl4AI method so no browser/network is used, and inject fake fetchers.

```python
# append to backend_ml/tests/test_scraper.py
from services.scraper import ScraperService, ScrapeResult, MIN_CONTENT_CHARS


class _SpyFetcher:
    def __init__(self, name, result):
        self.name = name
        self.enabled = True
        self.result = result
        self.called = False
    async def fetch(self, url):
        self.called = True
        return self.result


async def test_crawl4ai_sufficient_skips_fallback(monkeypatch):
    spy = _SpyFetcher("jina", "should not be used")
    svc = ScraperService(fallback_fetchers=[spy])
    rich = "x" * (MIN_CONTENT_CHARS + 50)
    async def fake_primary(url): return rich
    monkeypatch.setattr(svc, "_crawl4ai_scrape", fake_primary)
    res = await svc.scrape_with_provenance("https://x.org")
    assert res.method == "crawl4ai" and res.content == rich
    assert spy.called is False


async def test_falls_back_to_jina_when_crawl4ai_empty(monkeypatch):
    content = "y" * (MIN_CONTENT_CHARS + 10)
    spy = _SpyFetcher("jina", content)
    svc = ScraperService(fallback_fetchers=[spy])
    async def fake_primary(url): return "\n"        # the real bug shape
    monkeypatch.setattr(svc, "_crawl4ai_scrape", fake_primary)
    res = await svc.scrape_with_provenance("https://x.org")
    assert res.method == "jina" and res.content == content
    assert spy.called is True


async def test_all_fail_returns_none(monkeypatch):
    spy = _SpyFetcher("jina", None)
    svc = ScraperService(fallback_fetchers=[spy])
    async def fake_primary(url): return None
    monkeypatch.setattr(svc, "_crawl4ai_scrape", fake_primary)
    res = await svc.scrape_with_provenance("https://x.org")
    assert res.content is None and res.method == "none"


async def test_scrape_url_wrapper_returns_string(monkeypatch):
    svc = ScraperService(fallback_fetchers=[])
    rich = "z" * (MIN_CONTENT_CHARS + 1)
    async def fake_primary(url): return rich
    monkeypatch.setattr(svc, "_crawl4ai_scrape", fake_primary)
    assert await svc.scrape_url("https://x.org") == rich
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/test_scraper.py -k "fallback or provenance or wrapper or crawl4ai_sufficient or jina_when or all_fail" -v`
Expected: FAIL — `ImportError: cannot import name 'ScrapeResult'` / `_crawl4ai_scrape` missing.

- [ ] **Step 3: Refactor `scraper.py`.** Make these exact edits:

(a) Add imports + constants near the top (after existing imports):

```python
from dataclasses import dataclass

MIN_CONTENT_CHARS = 200   # below this, Crawl4AI output is "insufficient" → fallback


@dataclass
class ScrapeResult:
    content: Optional[str]
    method: str            # "crawl4ai" | "jina" | "firecrawl" | "none"
```

(b) Change `__init__` to accept an injectable chain:

```python
    def __init__(self, fallback_fetchers: Optional[list] = None):
        self._browser_config = BrowserConfig(headless=True, verbose=False)
        self._crawl_config = CrawlerRunConfig(
            word_count_threshold=10,
            exclude_external_links=True,
            remove_overlay_elements=True,
        )
        if fallback_fetchers is None:
            from services.fallback_fetcher import build_default_fallback_chain
            fallback_fetchers = build_default_fallback_chain()
        self._fallbacks = fallback_fetchers
```

(c) **Rename** the current `async def scrape_url(self, url)` to `async def _crawl4ai_scrape(self, url)` — keep its entire body verbatim (the two-phase shallow + deep-crawl logic and `return` statements are unchanged).

(d) Add the two new methods at the end of the class:

```python
    async def scrape_with_provenance(self, url: str) -> ScrapeResult:
        """Crawl4AI first; fall back through the chain; report which tool won."""
        primary = await self._crawl4ai_scrape(url)
        if primary and len(primary.strip()) >= MIN_CONTENT_CHARS:
            return ScrapeResult(primary, "crawl4ai")

        for fetcher in self._fallbacks:
            if not getattr(fetcher, "enabled", True):
                continue
            logger.info("Trying fallback fetcher",
                        extra={"event": "fallback_attempt", "url": url, "tool": fetcher.name})
            content = await fetcher.fetch(url)
            if content and len(content.strip()) >= MIN_CONTENT_CHARS:
                logger.info("Fallback succeeded",
                            extra={"event": "fallback_success", "url": url,
                                   "tool": fetcher.name, "content_length": len(content)})
                return ScrapeResult(content, fetcher.name)

        if primary and primary.strip():       # some content, just under threshold
            return ScrapeResult(primary, "crawl4ai")
        return ScrapeResult(None, "none")

    async def scrape_url(self, url: str) -> Optional[str]:
        """Backward-compatible wrapper (live pipeline uses this)."""
        return (await self.scrape_with_provenance(url)).content
```

- [ ] **Step 4: Run the new + existing scraper tests.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/test_scraper.py -v`
Expected: all PASS (new chain tests + the pre-existing tests, which call `scrape_url`/`_crawl4ai_scrape` via the unchanged Crawl4AI path). If a pre-existing test directly asserted the old `scrape_url` body, it still works because the body now lives in `_crawl4ai_scrape` and `scrape_url` delegates through it.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/services/scraper.py backend_ml/tests/test_scraper.py
git commit -m "feat(scraper): provenance-aware scrape_with_provenance + fallback chain"
```

---

## Task 3: Agent provenance (state + scrape node + persist)

**Files:**
- Modify: `backend_ml/agent/state.py`, `backend_ml/agent/nodes/scrape.py`, `backend_ml/agent/nodes/persist.py`
- Test: `backend_ml/tests/agent/test_scrape_node.py`, `backend_ml/tests/agent/test_persist_node.py`

- [ ] **Step 1: Write the failing tests.**

```python
# append to backend_ml/tests/agent/test_scrape_node.py
from agent.nodes.scrape import make_scrape_node
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
```

```python
# append to backend_ml/tests/agent/test_persist_node.py
async def test_persist_records_scrape_method(test_db):
    from datetime import datetime, timezone
    from agent.nodes.persist import make_persist_node
    GOOD = {"status": "OPEN", "hours_notes": "Mon 9-1", "hours_today": "9-1",
            "eligibility_rules": ["Open to all"], "is_id_required": False,
            "residency_req": None, "special_notes": None, "confidence": 8}
    await test_db["pantries"].insert_one({
        "name": "P", "address": "a", "lat": 1.0, "lng": 2.0, "hours_notes": "OLD",
        "status": "UNKNOWN", "confidence": 2, "source_url": "https://prov.org",
        "last_updated": datetime(2020, 1, 1, tzinfo=timezone.utc)})
    node = make_persist_node(db=test_db)
    await node({"source_url": "https://prov.org", "extracted_data": GOOD,
                "validation_errors": [], "confidence": 8, "scrape_method": "jina"})
    doc = await test_db["pantries"].find_one({"source_url": "https://prov.org"})
    assert doc["scrape_method"] == "jina"
```

- [ ] **Step 2: Run to verify they fail.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/agent/test_scrape_node.py tests/agent/test_persist_node.py -k "method or threads or none_marks" -v`
Expected: FAIL — node still calls `scrape_url`; persist hardcodes `"crawl4ai"`.

- [ ] **Step 3: Update the three source files.**

(a) `agent/state.py` — add to `ExtractionState`:

```python
    scrape_method: Optional[str]
```

(b) `agent/nodes/scrape.py` — replace the node body:

```python
# backend_ml/agent/nodes/scrape.py
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
```

(c) `agent/nodes/persist.py` — in the `update` dict, replace the hardcoded line:

```python
            "scrape_method": state.get("scrape_method", "crawl4ai"),
```

- [ ] **Step 4: Run the agent tests.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/agent/test_scrape_node.py tests/agent/test_persist_node.py -v`
Expected: all PASS (new + existing). Note: existing `test_scrape_node.py` used a `FakeScraper` with `scrape_url`; update those existing cases to use a provenance scraper, or keep `FakeScraper` and add a `scrape_with_provenance` method to it returning `ScrapeResult(markdown, "crawl4ai")`. Make `tests/agent/conftest.py`'s `FakeScraper` grow a `scrape_with_provenance` method so all callers work:

```python
# in tests/agent/conftest.py FakeScraper:
    async def scrape_with_provenance(self, url):
        from services.scraper import ScrapeResult
        md = await self.scrape_url(url)
        return ScrapeResult(md, "crawl4ai" if md else "none")
```

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/state.py backend_ml/agent/nodes/scrape.py backend_ml/agent/nodes/persist.py backend_ml/tests/agent/test_scrape_node.py backend_ml/tests/agent/test_persist_node.py backend_ml/tests/agent/conftest.py
git commit -m "feat(agent): thread scrape provenance into state + persist"
```

---

## Task 4: Optional capped `FirecrawlFetcher` (off by default)

**Files:**
- Create: `backend_ml/services/firecrawl_fetcher.py`
- Test: `backend_ml/tests/test_firecrawl_fetcher.py`

- [ ] **Step 1: Write the failing test** (mocks Mongo + the Firecrawl SDK; asserts the budget gate prevents billed calls).

```python
# backend_ml/tests/test_firecrawl_fetcher.py
from services.firecrawl_fetcher import FirecrawlFetcher


class _FakeColl:
    def __init__(self, count): self._count = count; self.inc_called = False
    async def find_one(self, q): return {"count": self._count} if self._count is not None else None
    async def update_one(self, q, u, upsert=False): self.inc_called = True


class _FakeDB:
    def __init__(self, coll): self._coll = coll
    def __getitem__(self, name): return self._coll


async def test_over_budget_skips_without_api_call(monkeypatch):
    coll = _FakeColl(count=400)
    f = FirecrawlFetcher(api_key="k", monthly_budget=400, db_getter=lambda: _FakeDB(coll))
    # If it tried to import/call the SDK we'd know; assert it returns None and never increments
    assert await f.fetch("https://x.org") is None
    assert coll.inc_called is False


async def test_no_key_returns_none():
    f = FirecrawlFetcher(api_key=None, monthly_budget=400, db_getter=lambda: _FakeDB(_FakeColl(0)))
    assert await f.fetch("https://x.org") is None


async def test_success_increments_counter(monkeypatch):
    coll = _FakeColl(count=10)
    f = FirecrawlFetcher(api_key="k", monthly_budget=400, db_getter=lambda: _FakeDB(coll))

    class _Res: markdown = "real content"
    class _FakeFC:
        def __init__(self, api_key): pass
        async def scrape(self, url, formats=None): return _Res()
    import services.firecrawl_fetcher as mod
    monkeypatch.setattr(mod, "_import_async_firecrawl", lambda: _FakeFC)

    out = await f.fetch("https://x.org")
    assert out == "real content"
    assert coll.inc_called is True
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/test_firecrawl_fetcher.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Write `firecrawl_fetcher.py`** (uses an injectable importer so tests don't need the real SDK).

```python
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
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/test_firecrawl_fetcher.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/services/firecrawl_fetcher.py backend_ml/tests/test_firecrawl_fetcher.py
git commit -m "feat(scraper): optional capped FirecrawlFetcher (off by default)"
```

---

## Task 5: Dependency bump + config doc

**Files:**
- Modify: `backend_ml/requirements.txt`

- [ ] **Step 1: Bump the Firecrawl pin.** In `requirements.txt`, change `firecrawl-py>=0.0.16` to:

```
firecrawl-py>=4.0
```

(`httpx` is already present for Jina; no other dep changes.)

- [ ] **Step 2: Verify the install resolves.**

Run: `cd backend_ml && ./venv/bin/pip install -r requirements.txt 2>&1 | tail -3`
Expected: requirements already satisfied / firecrawl-py 4.x present (`./venv/bin/pip show firecrawl-py | grep Version` → 4.x).

- [ ] **Step 3: Commit.**

```bash
git add backend_ml/requirements.txt
git commit -m "build: bump firecrawl-py to >=4.0 (v2 SDK)"
```

---

## Task 6: Full offline regression

**Files:** none (verification).

- [ ] **Step 1: Run the entire backend suite (excluding the live smoke).**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/ -q -m "not live"`
Expected: all green (existing suite + new fallback/firecrawl/provenance tests). If any pre-existing scraper/agent test broke due to the refactor, fix it to match the new `scrape_with_provenance`/`ScrapeResult` shapes (do not change product behavior).

- [ ] **Step 2: Register the `live` marker** so `-m "not live"` doesn't warn. Append to `backend_ml/pytest.ini`:

```ini
markers =
    live: tests that hit the network (opt-in via RUN_LIVE_SCRAPE=1)
```

- [ ] **Step 3: Commit (if pytest.ini changed).**

```bash
git add backend_ml/pytest.ini
git commit -m "test: register 'live' pytest marker"
```

---

## Task 7: Opt-in live smoke test

**Files:**
- Create: `backend_ml/tests/test_fallback_live.py`

- [ ] **Step 1: Write the live test** (skipped unless `RUN_LIVE_SCRAPE=1`).

```python
# backend_ml/tests/test_fallback_live.py
import os
import pytest

pytestmark = pytest.mark.live

RUN = os.getenv("RUN_LIVE_SCRAPE") == "1"
URL = "https://midtownassistancecenter.org"


@pytest.mark.skipif(not RUN, reason="set RUN_LIVE_SCRAPE=1 to run live network tests")
async def test_jina_recovers_failing_site():
    from services.fallback_fetcher import JinaReaderFetcher
    out = await JinaReaderFetcher(api_key=os.getenv("JINA_API_KEY")).fetch(URL)
    assert out is not None and len(out) > 1000


@pytest.mark.skipif(not RUN, reason="set RUN_LIVE_SCRAPE=1 to run live network tests")
async def test_scraper_uses_fallback_end_to_end():
    from services.scraper import ScraperService
    res = await ScraperService().scrape_with_provenance(URL)
    assert res.content is not None and len(res.content) > 200
    assert res.method in {"jina", "crawl4ai"}   # jina expected for this JS site
```

- [ ] **Step 2: Run it live** (controller provides `JINA_API_KEY` + flag).

Run: `cd backend_ml && RUN_LIVE_SCRAPE=1 ./venv/bin/python -m pytest tests/test_fallback_live.py -v`
Expected: 2 PASS — Jina returns >1000 chars; the scraper end-to-end recovers the site via the `jina` fallback. (This is the exact case failing before this work.)

- [ ] **Step 3: Confirm it's skipped by default.**

Run: `cd backend_ml && ./venv/bin/python -m pytest tests/test_fallback_live.py -v`
Expected: 2 SKIPPED.

- [ ] **Step 4: Commit.**

```bash
git add backend_ml/tests/test_fallback_live.py
git commit -m "test(scraper): opt-in live smoke proving Jina recovers JS sites"
```

---

## Task 8: ADR-021 + ADR-008 status

**Files:**
- Modify: `docs/decisions.md`

- [ ] **Step 1: Append ADR-021** (before the template section), full body:

  **ADR-021: Jina Reader as the free scraper fallback (refines ADR-008).**
  Context: Crawl4AI 0.8.9 returns empty markdown on JS/anti-bot pantry sites (verified: 1-char output on two live sites, even with JS-wait tuning, native and emulated); the user requires zero scraping cost. Decision: add a pluggable fallback chain in `ScraperService`; default to **Jina Reader** (`r.jina.ai`, free, verified to recover the failing sites) when Crawl4AI yields `< MIN_CONTENT_CHARS` (200). Firecrawl (ADR-008's intended fallback) is retained as an **opt-in, hard-capped** secondary that defaults off, so the standard config is $0. The public `scrape_url` interface is preserved (live discovery path benefits free); `scrape_with_provenance` adds per-tool provenance recorded as `scrape_method`. Consequences: new `scraper_usage` collection only if Firecrawl is enabled; `firecrawl-py` bumped to v4. Re-evaluation trigger: if Jina rate limits/quality become inadequate, reorder the chain or enable capped Firecrawl.

- [ ] **Step 2: Update ADR-008's status line** to: `**Status**: Accepted — superseded in part by ADR-021 (free fallback promoted)`.

- [ ] **Step 3: Commit.**

```bash
git add docs/decisions.md
git commit -m "docs: ADR-021 Jina free scraper fallback; update ADR-008 status"
```

---

## Self-Review (completed by plan author)

**Spec coverage:**
- §2 chain concept + `MIN_CONTENT_CHARS` → Task 2 ✓
- §3.1 `fallback_fetcher.py` (protocol, Jina, builder) → Task 1 ✓
- §3.2 `firecrawl_fetcher.py` capped/off → Task 4 ✓
- §3.3 `scraper.py` refactor (`ScrapeResult`, `_crawl4ai_scrape`, `scrape_with_provenance`, wrapper) → Task 2 ✓
- §3.4 agent scrape node + state + persist provenance → Task 3 ✓
- §4 config/env + requirements bump → Tasks 1 (env), 4 (env), 5 (deps) ✓
- §5 telemetry (logs + `scrape_method`) → Tasks 2, 3 ✓
- §6 error handling (fetchers swallow, chain exhaustion → None) → Tasks 1, 2, 4 ✓
- §7 testing (unit, scraper, agent, live opt-in, regression) → Tasks 1–4, 6, 7 ✓
- §8 ADR-021 → Task 8 ✓

**Placeholder scan:** none — all steps have concrete code/commands.

**Type consistency:** `ScrapeResult(content, method)` used identically in Tasks 2/3; `scrape_with_provenance` signature matches across scraper, scrape node, FakeScraper, and live test; `FallbackFetcher` has `name`/`enabled`/`fetch` consistently in Tasks 1/2/4; env var names (`JINA_ENABLED`, `JINA_API_KEY`, `FIRECRAWL_FALLBACK_ENABLED`, `FIRECRAWL_MONTHLY_BUDGET`, `MIN_CONTENT_CHARS`) match the spec.

**Known consideration:** Task 3 grows `FakeScraper` in `tests/agent/conftest.py` with `scrape_with_provenance` so all prior agent tests (subgraph, graph, smoke) keep working — the regression run in Task 6 is the safety net.
