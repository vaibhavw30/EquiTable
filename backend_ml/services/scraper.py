"""
Scraper Service - Uses Crawl4AI to extract main content from pantry websites.

Crawl4AI is the primary scraper (ADR-008). It is async-native, free,
and produces LLM-optimized Markdown output.

Firecrawl remains available as a dormant fallback (not imported at runtime).
"""

import logging
import time
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

logger = logging.getLogger("equitable")


class ScrapeError(Exception):
    """Raised when scraping fails after all attempts."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"Scrape failed for {url}: {reason}")


class ScraperService:
    """
    Service for scraping pantry websites using Crawl4AI.
    Extracts main content as Markdown for LLM extraction.
    """

    def __init__(self):
        self._browser_config = BrowserConfig(
            headless=True,
            verbose=False,
        )
        self._crawl_config = CrawlerRunConfig(
            word_count_threshold=10,
            exclude_external_links=True,
            remove_overlay_elements=True,
        )

    async def scrape_url(self, url: str) -> Optional[str]:
        """
        Scrape a URL and return its main content as Markdown.

        Args:
            url: The URL to scrape.

        Returns:
            The markdown content of the page, or None if scraping fails.
        """
        start = time.time()
        logger.info("Scrape starting", extra={"event": "scrape_start", "url": url, "tool": "crawl4ai"})

        try:
            async with AsyncWebCrawler(config=self._browser_config) as crawler:
                result = await crawler.arun(url=url, config=self._crawl_config)

            duration_ms = round((time.time() - start) * 1000, 2)

            if not result.success:
                error_msg = getattr(result, "error_message", "Unknown error")
                logger.error(
                    "Scrape failed",
                    extra={"event": "scrape_failed", "url": url, "tool": "crawl4ai", "error": error_msg, "duration_ms": duration_ms},
                )
                return None

            markdown = result.markdown_v2.raw_markdown if hasattr(result, "markdown_v2") and result.markdown_v2 else result.markdown

            if not markdown or len(markdown.strip()) < 20:
                logger.error(
                    "Scrape failed",
                    extra={"event": "scrape_failed", "url": url, "tool": "crawl4ai", "error": "Empty or minimal content", "duration_ms": duration_ms},
                )
                return None

            logger.info(
                "Scrape complete",
                extra={"event": "scrape_complete", "url": url, "tool": "crawl4ai", "content_length": len(markdown), "duration_ms": duration_ms},
            )
            return markdown

        except Exception as e:
            duration_ms = round((time.time() - start) * 1000, 2)
            logger.error(
                "Scrape failed",
                extra={"event": "scrape_failed", "url": url, "tool": "crawl4ai", "error": str(e), "duration_ms": duration_ms},
            )
            return None


# Singleton instance for reuse
_scraper_instance: Optional[ScraperService] = None


def get_scraper_service() -> ScraperService:
    """Get or create a singleton ScraperService instance."""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = ScraperService()
    return _scraper_instance
