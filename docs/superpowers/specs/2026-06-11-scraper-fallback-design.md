# Spec: Free-First Scraper Fallback Chain (Crawl4AI → Jina Reader)

**Date**: 2026-06-11
**Status**: Approved (design) — pending implementation plan
**Author**: Brainstorming session
**Owner boundary**: Scraping Quality (touches `services/scraper.py` + new `services/fallback_fetcher.py`)

---

## 0. Problem & Evidence

### The bug
The refresh agent (and the live discovery path) both call `ScraperService.scrape_url()`, which uses **Crawl4AI 0.8.9**. Against modern JS-rendered / anti-bot pantry sites, Crawl4AI returns `success=True` **but empty markdown** (`raw_markdown == "\n"`, length 1). The agent then correctly records a scrape failure and does **not** overwrite existing data — so the pantry is never refreshed.

### What we verified (live probes, 2026-06-11)
| Tool | `midtownassistancecenter.org` | `firstpresatl.org/community-ministries` | Cost |
|------|------------------------------|------------------------------------------|------|
| Crawl4AI 0.8.9 (current) | **1 char** (`"\n"`) | **1 char** | free |
| Crawl4AI + JS waits (`networkidle`, 3s delay, `scan_full_page`, `magic`) | **1 char** (all 5 variants) | — | free |
| **Jina Reader** (`r.jina.ai`, no key) | **3,291 chars** ✓ real content | **9,887 chars** ✓ real content | **free** |
| Firecrawl (cloud, v4 SDK) | 3,600 chars ✓ | — | paid per page |

**Conclusions:**
1. It is **not** a markdown-extraction code bug (`_extract_markdown` reads the right field; the content genuinely isn't captured) and **not** an amd64-emulation artifact (native arm64 was identically empty).
2. Crawl4AI cannot render these sites even with JS-wait tuning. They need a heavier renderer.
3. **Jina Reader recovers the content for free.** This is the basis of the design.

### Hard constraint (from the user)
**No paid scraping.** The default configuration must cost **$0**. Firecrawl (which works but bills per page) is therefore demoted to an optional, off-by-default, hard-capped secondary.

### Relationship to ADR-008
ADR-008 kept Firecrawl as a "dormant fallback, ready to promote if Crawl4AI fails >15%." We are at that trigger — but because of the no-pay constraint we promote a **free** fallback (Jina Reader) instead, and keep Firecrawl as the documented, capped, opt-in tier. ADR-021 records this.

---

## 1. Goal

Make `ScraperService` resilient to JS/anti-bot sites by adding a **pluggable fallback chain** that runs only when Crawl4AI returns insufficient content — defaulting to a **free** fallback (Jina Reader). The public `scrape_url(url) -> Optional[str]` interface is preserved so the live discovery path and ingestion pipeline are unchanged and benefit automatically. The agent additionally gets per-source **provenance** (which tool produced the content) for telemetry.

**Non-goals (explicitly out of scope):**
- The curator-LLM-ranker fallback bug (separate task).
- Investigating *why* Crawl4AI 0.8.9 regressed / pinning an older version (the fallback makes it moot).
- Re-architecting the live discovery path (it benefits transparently; we don't touch it).

---

## 2. Concept: the fallback chain

Think of scraping as an **ordered chain of fetchers**, each `url -> Optional[str]`, tried in order until one returns "enough" content:

```
scrape(url):
    content = crawl4ai_two_phase(url)            # existing, FREE, primary
    if sufficient(content): return (content, "crawl4ai")

    for fetcher in fallback_chain:               # default: [Jina]; optional: [Jina, Firecrawl]
        if fetcher.enabled:
            c = fetcher.fetch(url)               # FREE (Jina) or capped (Firecrawl;
                                                 #   returns None without an API call if over budget)
            if sufficient(c): return (c, fetcher.name)

    return (None, "none")                        # all failed → scrape fails, $0, no clobber
```

- **`sufficient(content)`** = `content is not None and len(content.strip()) >= MIN_CONTENT_CHARS` (default **200**). Below this, Crawl4AI is treated as "insufficient" and we fall through. 200 chars is comfortably above the empty `"\n"` failure and below any real pantry page.
- **Default chain = `[JinaReaderFetcher]`** → fully free.
- **Firecrawl** is a second fetcher, `enabled=False` by default, gated by a persistent monthly budget so it can *never* bill beyond a configured free allotment.

This is the "Crawl4AI-first, free-fallback" architecture the user approved, refined to free-first after the Jina probe.

---

## 3. Components & file structure

### 3.1 New file: `backend_ml/services/fallback_fetcher.py`

Defines the fetcher interface and the concrete fetchers. One clear responsibility: "given a URL, return clean markdown (or None) from a secondary source."

```python
"""Fallback content fetchers used when Crawl4AI returns insufficient content.

Each fetcher implements `async fetch(url) -> Optional[str]` returning clean
markdown, or None on failure. Fetchers are tried in order by ScraperService.
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
    # Budget/cost enforcement (if any) lives INSIDE fetch(): a fetcher over its
    # budget returns None without making a billable call.


class JinaReaderFetcher:
    """Free JS-rendering reader via https://r.jina.ai/{url}.

    No API key required (IP-rate-limited ~20 rpm). An optional free JINA_API_KEY
    raises the limit. Returns markdown text. Retries with backoff on HTTP 429.
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


def build_default_fallback_chain() -> list[FallbackFetcher]:
    """Construct the fallback chain from environment. Default = [Jina] (free)."""
    chain: list[FallbackFetcher] = []
    if _bool_env("JINA_ENABLED", True):
        chain.append(JinaReaderFetcher(
            api_key=os.getenv("JINA_API_KEY"),  # optional, free
            enabled=True,
        ))
    if _bool_env("FIRECRAWL_FALLBACK_ENABLED", False):  # OFF by default → $0
        from services.firecrawl_fetcher import FirecrawlFetcher  # lazy import
        chain.append(FirecrawlFetcher.from_env())
    return chain


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}
```

**Implementation advice / gotchas:**
- `r.jina.ai/{url}` — the URL is appended raw (Jina handles encoding). Pass the full `https://…` URL.
- Jina's default body has a small `Title: / URL Source: / Markdown Content:` preamble. **Keep it** — it's useful context for the LLM extractor and harmless. Do not strip.
- Jina renders the page server-side (can take 5–30 s). The 45 s timeout accommodates this.
- Rate limits: without a key, ~20 rpm per IP. With `MAX_CONCURRENT=4` and ≤25 sources/run that's fine, but the 429 backoff is the safety net. Recommend the user grab a **free** `JINA_API_KEY` for headroom (optional).

### 3.2 Optional file: `backend_ml/services/firecrawl_fetcher.py` (off by default)

Implemented for completeness and to honor ADR-008's path, but **disabled by default** and **hard-capped** so it can never bill beyond a configured allotment.

```python
"""OPTIONAL paid fallback. Disabled unless FIRECRAWL_FALLBACK_ENABLED=true.

Hard monthly budget (persisted in Mongo `scraper_usage`) guarantees the number
of Firecrawl pages never exceeds FIRECRAWL_MONTHLY_BUDGET — so it never bills
beyond the configured (free-tier-sized) allotment.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("equitable")


class FirecrawlFetcher:
    name = "firecrawl"

    def __init__(self, api_key: str, monthly_budget: int, db_getter, enabled: bool = True):
        self._api_key = api_key
        self._monthly_budget = monthly_budget
        self._db_getter = db_getter        # callable -> Motor database (for the counter)
        self.enabled = enabled

    @classmethod
    def from_env(cls):
        key = os.getenv("FIRECRAWL_API_KEY") or os.getenv("FIRECRAWL_KEY")
        budget = int(os.getenv("FIRECRAWL_MONTHLY_BUDGET", "400"))  # < free tier
        from database import get_database
        return cls(api_key=key, monthly_budget=budget, db_getter=get_database, enabled=True)

    def _month_key(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    async def _used_this_month(self) -> int:
        doc = await self._db_getter()["scraper_usage"].find_one({"_id": f"firecrawl:{self._month_key()}"})
        return (doc or {}).get("count", 0)

    async def fetch(self, url: str) -> Optional[str]:
        if not self._api_key:
            return None
        used = await self._used_this_month()
        if used >= self._monthly_budget:
            logger.warning("Firecrawl monthly budget exhausted — skipping (no charge)",
                           extra={"event": "firecrawl_budget_exhausted",
                                  "used": used, "budget": self._monthly_budget})
            return None
        try:
            from firecrawl import AsyncFirecrawl
            fc = AsyncFirecrawl(api_key=self._api_key)
            res = await fc.scrape(url, formats=["markdown"])
            md = getattr(res, "markdown", None)
            if md and md.strip():
                # increment the monthly counter atomically AFTER a successful billed call
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

**Why this guarantees "no pay":** the counter is checked *before* every call and incremented *after* every successful (billed) page. Once `count >= FIRECRAWL_MONTHLY_BUDGET`, the fetcher returns `None` without calling the API. Set `FIRECRAWL_MONTHLY_BUDGET` ≤ your plan's free allotment (default 400, under the common 500 free) and it can never exceed it. And because `FIRECRAWL_FALLBACK_ENABLED` defaults to `false`, this code does not even load by default.

### 3.3 Modified: `backend_ml/services/scraper.py`

Add provenance + the fallback chain while preserving the existing public interface.

```python
from dataclasses import dataclass

MIN_CONTENT_CHARS = 200   # below this, Crawl4AI output is "insufficient" → fallback

@dataclass
class ScrapeResult:
    content: Optional[str]
    method: str            # "crawl4ai" | "jina" | "firecrawl" | "none"
```

`ScraperService.__init__` gains an injected chain (defaulting to the env-built one):

```python
def __init__(self, fallback_fetchers: Optional[list] = None):
    ...  # existing browser/crawl config
    if fallback_fetchers is None:
        from services.fallback_fetcher import build_default_fallback_chain
        fallback_fetchers = build_default_fallback_chain()
    self._fallbacks = fallback_fetchers
```

New provenance-aware method (the agent uses this); `scrape_url` becomes a thin wrapper (live pipeline keeps using it):

```python
async def scrape_with_provenance(self, url: str) -> ScrapeResult:
    # 1) existing Crawl4AI two-phase attempt → `primary` (Optional[str])
    primary = await self._crawl4ai_scrape(url)   # refactor current scrape_url body into this
    if primary and len(primary.strip()) >= MIN_CONTENT_CHARS:
        return ScrapeResult(primary, "crawl4ai")

    # 2) fallback chain (default: Jina, free)
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

    # 3) crawl4ai produced *some* content but < threshold? prefer it over nothing
    if primary and primary.strip():
        return ScrapeResult(primary, "crawl4ai")
    return ScrapeResult(None, "none")

async def scrape_url(self, url: str) -> Optional[str]:
    """Backward-compatible: returns markdown or None (live pipeline uses this)."""
    return (await self.scrape_with_provenance(url)).content
```

**Refactor note:** the current `scrape_url` body (shallow + deep-crawl logic) moves verbatim into a private `_crawl4ai_scrape(url) -> Optional[str]`. No behavior change to the Crawl4AI path. Optionally tidy the dead `markdown_v2` references in `_extract_markdown`/`_aggregate_pages` to use `result.markdown` directly (Crawl4AI 0.8.x `StringCompatibleMarkdown`), but that is cleanup, not the fix.

### 3.4 Modified: `backend_ml/agent/nodes/scrape.py` (provenance)

The agent scrape node calls the provenance method and threads `method` into state so `persist` can record real provenance:

```python
async def scrape_node(state):
    start = time.time()
    result = await scraper.scrape_with_provenance(state["source_url"])
    latency_ms = round((time.time() - start) * 1000, 2)
    if not result.content:
        return {"raw_markdown": None, "latency_ms": latency_ms, "outcome": "failed"}
    return {"raw_markdown": result.content, "scrape_method": result.method, "latency_ms": latency_ms}
```

Add `scrape_method: Optional[str]` to `ExtractionState`, and in `persist.py` use `state.get("scrape_method", "crawl4ai")` instead of the hardcoded `"crawl4ai"`.

---

## 4. Configuration (env)

| Var | Default | Meaning |
|-----|---------|---------|
| `JINA_ENABLED` | `true` | Enable the free Jina Reader fallback |
| `JINA_API_KEY` | _(unset)_ | Optional **free** key for higher Jina rate limits |
| `FIRECRAWL_FALLBACK_ENABLED` | `false` | Enable the optional paid Firecrawl fallback (off → $0) |
| `FIRECRAWL_API_KEY` / `FIRECRAWL_KEY` | _(either)_ | Firecrawl key (only read if enabled); both names supported |
| `FIRECRAWL_MONTHLY_BUDGET` | `400` | Hard monthly page cap if Firecrawl enabled (set ≤ free tier) |
| `MIN_CONTENT_CHARS` | `200` | Threshold below which Crawl4AI is "insufficient" |

**Default deployment = Crawl4AI + Jina = $0.** Firecrawl only ever runs if a human explicitly sets `FIRECRAWL_FALLBACK_ENABLED=true`, and even then is hard-capped.

`requirements.txt`: bump `firecrawl-py>=0.0.16` → `firecrawl-py>=4.0` (only imported when enabled); `httpx` is already a dependency (used by Jina).

---

## 5. Telemetry

- Structured logs: `fallback_attempt`, `fallback_success` (with `tool`, `content_length`), `jina_429`, `firecrawl_budget_exhausted`.
- Per-pantry `scrape_method` records the winning tool → you can query Mongo for the crawl4ai-vs-jina split and decide later whether to reorder the chain.
- `source_metrics.last_model_used` already exists; consider adding a `last_scrape_tool` later (not required now).

---

## 6. Error handling

- Each fetcher swallows its own exceptions and returns `None` (never raises into the chain).
- Chain exhaustion → `ScrapeResult(None, "none")` → agent records `outcome="failed"`, **no DB clobber** (unchanged behavior).
- Jina 429 / network → bounded exponential backoff, then `None`.
- Firecrawl over budget or keyless → `None` without an API call (no charge).
- The live ingestion pipeline (`_scrape`) still raises `IngestionError("scrape", ...)` on `None`, unchanged.

---

## 7. Testing requirements

All offline/deterministic except the explicitly-marked live smoke.

### Unit — `tests/test_fallback_fetcher.py`
- `JinaReaderFetcher.fetch`: mock `httpx.AsyncClient.get` to return a 200 body → returns the text; empty body → `None`; 429 then 200 → retries then succeeds; all-429 → `None` after `max_retries`. (Patch `asyncio.sleep` to avoid real delays.)
- `build_default_fallback_chain`: default → `[JinaReaderFetcher]`; `FIRECRAWL_FALLBACK_ENABLED=true` → includes `FirecrawlFetcher`; `JINA_ENABLED=false` → excludes Jina.
- `FirecrawlFetcher`: counter `>= budget` → `fetch` returns `None` **without** constructing the client (assert no network); successful path increments the counter (mock Mongo + `AsyncFirecrawl`).

### Unit — `tests/test_scraper.py` (extend)
- Inject a fake Crawl4AI result that yields rich content (≥200 chars) → `scrape_with_provenance` returns `method="crawl4ai"`, **no** fallback fetcher called (use a spy fetcher asserting `fetch` not awaited).
- Crawl4AI yields `"\n"` (the real bug) + a fake fallback returning 500 chars → result `method="jina"` content from fallback.
- Crawl4AI thin + fallback returns `None` → `ScrapeResult(None, "none")`.
- `scrape_url` wrapper returns `.content` (string or None) for backward-compat.
- **Existing** `test_scraper.py` cases must still pass — inject `fallback_fetchers=[]` where they assert the pure Crawl4AI path, so the chain doesn't change their expectations.

### Unit — agent nodes
- `tests/agent/test_scrape_node.py`: `scrape_with_provenance` returns content+method → node sets `raw_markdown` + `scrape_method`; returns `None` → `outcome="failed"`.
- `tests/agent/test_persist_node.py`: `persist` writes `scrape_method` from state (e.g. `"jina"`), not hardcoded.

### Live smoke (opt-in) — `tests/test_fallback_live.py`
- Marked `@pytest.mark.live` (skipped unless `RUN_LIVE_SCRAPE=1`). `JinaReaderFetcher().fetch("https://midtownassistancecenter.org")` → length > 1000; `ScraperService().scrape_with_provenance(same)` → `method in {"jina"}` and content > 200. This is the exact case failing today.

### Regression guard
All existing backend tests (`test_smoke.py`, `test_scraper.py`, `test_discovery_*.py`, `tests/agent/*`) stay green.

---

## 8. ADR

**ADR-021: Jina Reader as the free scraper fallback (refines ADR-008).**
Context: Crawl4AI 0.8.9 returns empty markdown on JS/anti-bot pantry sites; user requires zero scraping cost. Decision: add a pluggable fallback chain; default to **Jina Reader** (free, verified) when Crawl4AI yields `< MIN_CONTENT_CHARS`. Firecrawl (ADR-008's intended fallback) is retained as an **opt-in, hard-capped** secondary that defaults off, so the standard config is $0. Consequences: a new `scraper_usage` collection (only if Firecrawl enabled); `scrape_method` now records the real tool; the live discovery path gains JS-site resilience for free. Re-evaluation trigger: if Jina rate limits/quality become inadequate, reorder the chain or enable capped Firecrawl.

Also flip ADR-008's status line to "Superseded in part by ADR-021 (free fallback promoted)."

---

## 9. Sequencing (for the plan)

1. `fallback_fetcher.py` — `FallbackFetcher` protocol + `JinaReaderFetcher` + `build_default_fallback_chain` (+ unit tests). **Free path first.**
2. `scraper.py` — refactor Crawl4AI body into `_crawl4ai_scrape`; add `ScrapeResult` + `scrape_with_provenance`; keep `scrape_url` wrapper (+ tests).
3. Agent `scrape_node` + `ExtractionState.scrape_method` + `persist` provenance (+ tests).
4. `firecrawl_fetcher.py` (off-by-default, capped) + `scraper_usage` + tests.
5. Config/env wiring + `requirements.txt` bump.
6. Live opt-in smoke test.
7. ADR-021 + ADR-008 status update.

---

## 10. Risks & open questions

- **Jina availability/rate limits:** it's a free public service; could throttle or be down. Mitigations: 429 backoff, optional free `JINA_API_KEY`, `MAX_CONCURRENT=4`, and a failed scrape just retries next daily run (no clobber). If reliability matters more, enable capped Firecrawl.
- **Jina latency:** 5–30 s/page (server-side render). Fine for a background batch; the agent's per-run cost/time budget already tolerates this.
- **Content quality differences:** Jina includes nav/boilerplate; the Gemini extractor + confidence scoring already handle noisy markdown (it's what Crawl4AI produced too). The `food_relevance_score` gate in Crawl4AI does not apply to fallback output — fallbacks return content directly; the LLM + validator judge quality downstream.
- **Singleton + concurrency:** `ScraperService` is a singleton shared by concurrent subgraphs. The chain is stateless per-call (no shared mutable state on the instance), and the Firecrawl counter uses atomic Mongo `$inc`, so concurrent calls are safe.
- **Self-hosting Firecrawl** (open-source) is a future fully-free-at-scale option if Jina is outgrown; noted, not in scope.
