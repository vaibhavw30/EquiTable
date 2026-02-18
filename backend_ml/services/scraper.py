"""
Scraper Service - Uses Crawl4AI to extract main content from pantry websites.

Crawl4AI is the primary scraper (ADR-008). It is async-native, free,
and produces LLM-optimized Markdown output.

Two-phase scraping:
  Phase 1: Shallow scrape of the root URL (~3-5s)
  Phase 2: BFS deep crawl if root lacks food-pantry content (~10-15s extra)

Firecrawl remains available as a dormant fallback (not imported at runtime).
"""

import logging
import re
import time
from typing import Optional
from urllib.parse import urlparse

from crawl4ai import (
    AsyncWebCrawler,
    BFSDeepCrawlStrategy,
    BrowserConfig,
    CrawlerRunConfig,
    DomainFilter,
    FilterChain,
    KeywordRelevanceScorer,
    URLPatternFilter,
)

logger = logging.getLogger("equitable")

# Phrases that signal food-pantry-specific content
_FOOD_SIGNALS = [
    # Core food program terms
    "food pantry", "food bank", "food distribution", "food assistance",
    "food program", "food closet", "food shelf", "food ministry",
    "food rescue", "food drive", "food insecurity", "food access",
    "food desert", "food stamp", "snap benefits", "wic program",
    "feeding program", "meal program", "soup kitchen", "community kitchen",
    "free food", "free meals", "free groceries", "hot meals",
    # Schedule and hours
    "hours of operation", "distribution hours", "pantry hours",
    "distribution schedule", "serving hours", "open hours",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "weekly", "monthly", "biweekly", "every week", "every month",
    "1st and 3rd", "2nd and 4th", "first and third", "second and fourth",
    # Eligibility and requirements
    "eligibility", "requirements", "proof of residence", "proof of address",
    "open to all", "no questions asked", "bring id", "photo id",
    "income guidelines", "income limit", "below poverty", "low income",
    "referral required", "appointment only", "sign up", "pre-register",
    "zip code", "service area", "must reside", "county residents",
    # Food types
    "canned goods", "fresh produce", "groceries", "meals",
    "non-perishable", "perishable", "frozen food", "dairy",
    "bread", "vegetables", "fruits", "protein", "meat",
    "baby formula", "diapers", "hygiene products", "toiletries",
    # Organizations and context
    "salvation army", "united way", "feeding america", "second harvest",
    "harvest hope", "community action", "social services",
    "donate food", "volunteer", "food donation", "hunger",
    "families in need", "those in need", "underserved",
]

_FOOD_SIGNAL_PATTERN = re.compile(
    "|".join(re.escape(s) for s in _FOOD_SIGNALS), re.IGNORECASE
)

# URL path patterns likely to contain food pantry info
_FOOD_PATH_PATTERNS = [
    "*food*", "*pantry*", "*services*", "*programs*", "*hours*",
    "*about*", "*assistance*", "*resources*", "*help*", "*outreach*",
    "*ministry*", "*ministries*", "*community*", "*meals*", "*hunger*",
    "*donate*", "*volunteer*", "*schedule*", "*calendar*", "*contact*",
    "*eligibility*", "*faq*", "*info*", "*get-help*", "*need-help*",
]

MAX_AGGREGATE_CHARS = 30_000


def food_relevance_score(markdown: str) -> float:
    """
    Score 0.0-1.0 indicating density of food-pantry signal phrases.

    Uses a diminishing-returns formula: each additional match contributes
    less. 10+ matches → ~1.0.
    """
    if not markdown:
        return 0.0
    text_lower = markdown.lower()
    hits = len(_FOOD_SIGNAL_PATTERN.findall(text_lower))
    if hits == 0:
        return 0.0
    # Sigmoid-like: 10 hits ≈ 0.91, 5 hits ≈ 0.71, 2 hits ≈ 0.44
    return hits / (hits + 4.0)


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

    RELEVANCE_THRESHOLD = 0.7

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

    def _build_deep_strategy(self, url: str) -> BFSDeepCrawlStrategy:
        """Build a BFS deep crawl strategy scoped to the root domain."""
        domain = urlparse(url).netloc
        return BFSDeepCrawlStrategy(
            max_depth=1,
            max_pages=5,
            filter_chain=FilterChain(filters=[
                DomainFilter(allowed_domains=[domain]),
                URLPatternFilter(patterns=_FOOD_PATH_PATTERNS, use_glob=True),
            ]),
            url_scorer=KeywordRelevanceScorer(
                keywords=["food", "pantry", "services", "hours", "programs",
                          "assistance", "resources", "eligibility", "outreach",
                          "meals", "hunger", "help", "community", "schedule",
                          "donate", "volunteer", "ministry", "calendar", "contact"],
            ),
        )

    @staticmethod
    def _extract_markdown(result) -> Optional[str]:
        """Extract markdown from a CrawlResult, preferring v2."""
        if hasattr(result, "markdown_v2") and result.markdown_v2:
            return result.markdown_v2.raw_markdown
        return result.markdown

    @staticmethod
    def _aggregate_pages(results, root_url: str) -> Optional[str]:
        """
        Combine markdown from multiple crawl results.
        Root page appears first, then subpages sorted by content length (desc).
        Total output capped at MAX_AGGREGATE_CHARS.
        """
        root_parts = []
        sub_parts = []

        for r in results:
            if not r.success:
                continue
            md = r.markdown_v2.raw_markdown if hasattr(r, "markdown_v2") and r.markdown_v2 else r.markdown
            if not md or len(md.strip()) < 20:
                continue
            page_url = getattr(r, "url", root_url)
            entry = (page_url, md)
            if page_url.rstrip("/") == root_url.rstrip("/"):
                root_parts.append(entry)
            else:
                sub_parts.append(entry)

        # Sort subpages by content length descending (richest content first)
        sub_parts.sort(key=lambda x: len(x[1]), reverse=True)
        ordered = root_parts + sub_parts

        if not ordered:
            return None

        sections = []
        total = 0
        for page_url, md in ordered:
            header = f"\n\n---\n## Content from: {page_url}\n\n"
            section = header + md
            if total + len(section) > MAX_AGGREGATE_CHARS:
                remaining = MAX_AGGREGATE_CHARS - total
                if remaining > 200:  # Only include if meaningful
                    sections.append(section[:remaining])
                break
            sections.append(section)
            total += len(section)

        return "".join(sections).strip() if sections else None

    async def scrape_url(self, url: str) -> Optional[str]:
        """
        Scrape a URL and return its main content as Markdown.

        Two-phase approach:
          1. Shallow scrape of root URL
          2. If root lacks food relevance (< 0.7), BFS deep crawl for subpages

        Args:
            url: The URL to scrape.

        Returns:
            The markdown content (possibly aggregated from multiple pages),
            or None if scraping fails.
        """
        start = time.time()
        logger.info("Scrape starting", extra={"event": "scrape_start", "url": url, "tool": "crawl4ai"})

        try:
            async with AsyncWebCrawler(config=self._browser_config) as crawler:
                # Phase 1: Shallow scrape of root
                result = await crawler.arun(url=url, config=self._crawl_config)

                duration_ms = round((time.time() - start) * 1000, 2)

                if not result.success:
                    error_msg = getattr(result, "error_message", "Unknown error")
                    logger.error(
                        "Scrape failed",
                        extra={"event": "scrape_failed", "url": url, "tool": "crawl4ai",
                               "error": error_msg, "duration_ms": duration_ms},
                    )
                    return None

                root_markdown = self._extract_markdown(result)

                if not root_markdown or len(root_markdown.strip()) < 20:
                    logger.error(
                        "Scrape failed",
                        extra={"event": "scrape_failed", "url": url, "tool": "crawl4ai",
                               "error": "Empty or minimal content", "duration_ms": duration_ms},
                    )
                    return None

                # Check food relevance — skip deep crawl if root is rich enough
                relevance = food_relevance_score(root_markdown)
                logger.info(
                    "Food relevance scored",
                    extra={"event": "relevance_score", "url": url, "score": round(relevance, 3)},
                )

                if relevance >= self.RELEVANCE_THRESHOLD:
                    logger.info(
                        "Scrape complete (root sufficient)",
                        extra={"event": "scrape_complete", "url": url, "tool": "crawl4ai",
                               "content_length": len(root_markdown), "duration_ms": duration_ms,
                               "deep_crawl": False},
                    )
                    return root_markdown

                # Phase 2: Deep crawl for subpages
                logger.info("Deep crawl starting", extra={"event": "deep_crawl_start", "url": url})
                deep_start = time.time()

                strategy = self._build_deep_strategy(url)
                deep_results = await strategy.arun(
                    start_url=url, crawler=crawler, config=self._crawl_config,
                )

                deep_duration_ms = round((time.time() - deep_start) * 1000, 2)

                aggregated = self._aggregate_pages(deep_results, url)

                if aggregated and len(aggregated) > len(root_markdown):
                    total_duration_ms = round((time.time() - start) * 1000, 2)
                    logger.info(
                        "Scrape complete (deep crawl)",
                        extra={"event": "scrape_complete", "url": url, "tool": "crawl4ai",
                               "content_length": len(aggregated), "duration_ms": total_duration_ms,
                               "deep_crawl": True, "deep_crawl_ms": deep_duration_ms},
                    )
                    return aggregated

                # Fallback to root markdown if deep crawl added nothing
                total_duration_ms = round((time.time() - start) * 1000, 2)
                logger.info(
                    "Scrape complete (deep crawl no improvement)",
                    extra={"event": "scrape_complete", "url": url, "tool": "crawl4ai",
                           "content_length": len(root_markdown), "duration_ms": total_duration_ms,
                           "deep_crawl": True, "deep_crawl_improved": False},
                )
                return root_markdown

        except Exception as e:
            duration_ms = round((time.time() - start) * 1000, 2)
            logger.error(
                "Scrape failed",
                extra={"event": "scrape_failed", "url": url, "tool": "crawl4ai",
                       "error": str(e), "duration_ms": duration_ms},
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
