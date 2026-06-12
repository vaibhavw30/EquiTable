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
                    if attempt < self._max_retries:
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


def build_default_fallback_chain() -> list[FallbackFetcher]:
    """Construct the fallback chain from environment. Default = [Jina] (free)."""
    chain: list[FallbackFetcher] = []
    if _bool_env("JINA_ENABLED", True):
        chain.append(JinaReaderFetcher(api_key=os.getenv("JINA_API_KEY"), enabled=True))
    if _bool_env("FIRECRAWL_FALLBACK_ENABLED", False):  # OFF by default → $0
        from services.firecrawl_fetcher import FirecrawlFetcher
        chain.append(FirecrawlFetcher.from_env())
    return chain
