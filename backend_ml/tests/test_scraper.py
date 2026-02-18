"""
Tests for the ScraperService.
All tests use mocked Crawl4AI — no live HTTP calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.scraper import ScraperService, food_relevance_score


# Default markdown with food signals so existing tests trigger early-exit (no deep crawl)
_FOOD_RICH_MARKDOWN = (
    "# Community Food Pantry\n"
    "Hours of operation: Monday 9am-5pm, Tuesday 10am-4pm, Wednesday 9am-5pm, "
    "Thursday 10am-4pm, Friday 9am-12pm\n"
    "Open to all residents. Eligibility: bring photo ID and proof of address.\n"
    "Fresh produce, canned goods, and groceries available.\n"
    "Food distribution every week. Food assistance for families in need."
)


def _make_crawl_result(success=True, markdown=None, error_message=None, url=None):
    """Build a mock CrawlResult."""
    result = MagicMock()
    result.success = success
    result.markdown = markdown if markdown is not None else _FOOD_RICH_MARKDOWN
    result.markdown_v2 = None
    result.error_message = error_message
    result.url = url or "https://example.com"
    return result


def _make_crawler_mock(results):
    """
    Build an AsyncWebCrawler mock.

    Args:
        results: a single CrawlResult or list of them.
                 If a single result, arun returns it.
                 If a list, arun returns them in sequence (side_effect).
    """
    instance = AsyncMock()
    if isinstance(results, list):
        instance.arun = AsyncMock(side_effect=results)
    else:
        instance.arun = AsyncMock(return_value=results)
    instance.__aenter__ = AsyncMock(return_value=instance)
    instance.__aexit__ = AsyncMock(return_value=False)
    return instance


class TestScraperService:
    @pytest.fixture
    def scraper(self):
        return ScraperService()

    @pytest.mark.asyncio
    async def test_returns_markdown_on_success(self, scraper):
        mock_result = _make_crawl_result(markdown="# Food Pantry\nOpen Mon-Fri 9am-5pm. "
                                                   "Food distribution hours of operation. "
                                                   "Eligibility open to all. Fresh produce and groceries.")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            MockCrawler.return_value = _make_crawler_mock(mock_result)
            result = await scraper.scrape_url("https://example.com/pantry")

        assert result is not None
        assert "Food Pantry" in result

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, scraper):
        mock_result = _make_crawl_result(success=False, markdown=None, error_message="Connection refused")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            MockCrawler.return_value = _make_crawler_mock(mock_result)
            result = await scraper.scrape_url("https://down-site.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_content(self, scraper):
        mock_result = _make_crawl_result(markdown="")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            MockCrawler.return_value = _make_crawler_mock(mock_result)
            result = await scraper.scrape_url("https://empty-site.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_minimal_content(self, scraper):
        """Content under 20 chars is treated as empty."""
        mock_result = _make_crawl_result(markdown="hi")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            MockCrawler.return_value = _make_crawler_mock(mock_result)
            result = await scraper.scrape_url("https://minimal-site.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, scraper):
        """Scraper should catch exceptions and return None."""
        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(side_effect=TimeoutError("Timed out"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            result = await scraper.scrape_url("https://slow-site.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_prefers_markdown_v2_when_available(self, scraper):
        """If markdown_v2 is available, use raw_markdown from it."""
        mock_result = _make_crawl_result(markdown="old markdown")
        mock_v2 = MagicMock()
        mock_v2.raw_markdown = (
            "# Better Food Pantry\nClean content from v2. "
            "Hours of operation Monday Tuesday Wednesday Thursday Friday. "
            "Food distribution. Eligibility open to all. Groceries and fresh produce."
        )
        mock_result.markdown_v2 = mock_v2

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            MockCrawler.return_value = _make_crawler_mock(mock_result)
            result = await scraper.scrape_url("https://example.com")

        assert result is not None
        assert "Better Food Pantry" in result


class TestFoodRelevanceScoring:
    def test_high_relevance_content(self):
        """Content rich in food pantry signals scores high."""
        score = food_relevance_score(_FOOD_RICH_MARKDOWN)
        assert score >= 0.7

    def test_low_relevance_content(self):
        """Generic church homepage with minimal food content scores low."""
        generic = (
            "# Welcome to Grace Fellowship\n"
            "Join us for worship every Sunday at 10am.\n"
            "Our mission is to serve the community through faith and love.\n"
            "Contact us at info@grace.org for more information."
        )
        score = food_relevance_score(generic)
        assert score < 0.7

    def test_zero_relevance(self):
        """Completely unrelated content scores 0."""
        score = food_relevance_score("Buy our premium software today! Click here for deals.")
        assert score == 0.0

    def test_empty_string(self):
        score = food_relevance_score("")
        assert score == 0.0

    def test_none_input(self):
        score = food_relevance_score(None)
        assert score == 0.0


class TestDeepScraping:
    @pytest.fixture
    def scraper(self):
        return ScraperService()

    @pytest.mark.asyncio
    async def test_deep_crawl_triggered_on_low_relevance(self, scraper):
        """A generic root page triggers deep crawl for subpages."""
        generic_root = _make_crawl_result(
            markdown="# Welcome to Our Church\nJoin us for worship every Sunday at 10am. "
                     "We are a community of faith serving since 1950. Contact us for info.",
            url="https://church.org",
        )

        # Deep crawl returns a food-rich subpage
        food_subpage = _make_crawl_result(
            markdown=_FOOD_RICH_MARKDOWN,
            url="https://church.org/food-pantry",
        )
        deep_results = MagicMock()
        deep_results.__iter__ = MagicMock(return_value=iter([generic_root, food_subpage]))

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=generic_root)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            with patch.object(scraper, "_build_deep_strategy") as mock_strategy_builder:
                mock_strategy = AsyncMock()
                mock_strategy.arun = AsyncMock(return_value=deep_results)
                mock_strategy_builder.return_value = mock_strategy

                result = await scraper.scrape_url("https://church.org")

        assert result is not None
        assert "Food Pantry" in result or "food-pantry" in result
        mock_strategy.arun.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_deep_crawl_on_high_relevance(self, scraper):
        """Food-rich root page skips deep crawl — only one arun call."""
        rich_result = _make_crawl_result(markdown=_FOOD_RICH_MARKDOWN)

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=rich_result)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            with patch.object(scraper, "_build_deep_strategy") as mock_strategy_builder:
                result = await scraper.scrape_url("https://food-pantry.org")

        assert result is not None
        assert "Food Pantry" in result
        # Deep crawl strategy should never be called
        mock_strategy_builder.assert_not_called()

    def test_aggregate_respects_char_limit(self):
        """Aggregated output must not exceed MAX_AGGREGATE_CHARS."""
        results = []
        for i in range(10):
            r = _make_crawl_result(
                markdown="x" * 10_000,
                url=f"https://example.com/page{i}",
            )
            results.append(r)

        aggregated = ScraperService._aggregate_pages(results, "https://example.com/page0")
        assert aggregated is not None
        assert len(aggregated) <= 30_000

    def test_aggregate_prioritizes_root_page(self):
        """Root page content appears first in aggregated output."""
        root = _make_crawl_result(
            markdown="ROOT PAGE CONTENT here with enough chars to pass the threshold okay",
            url="https://example.com",
        )
        sub = _make_crawl_result(
            markdown="SUBPAGE CONTENT with enough characters to pass the twenty char min",
            url="https://example.com/services",
        )

        aggregated = ScraperService._aggregate_pages([sub, root], "https://example.com")
        assert aggregated is not None
        root_pos = aggregated.index("ROOT PAGE CONTENT")
        sub_pos = aggregated.index("SUBPAGE CONTENT")
        assert root_pos < sub_pos

    @pytest.mark.asyncio
    async def test_deep_crawl_fallback_to_root(self, scraper):
        """If deep crawl returns empty results, fall back to root markdown."""
        generic_root = _make_crawl_result(
            markdown="# Our Organization\nWe provide community services and outreach programs. "
                     "Located downtown, serving the area since 1985. Call for more details.",
            url="https://org.com",
        )

        empty_deep = MagicMock()
        empty_deep.__iter__ = MagicMock(return_value=iter([]))

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=generic_root)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            with patch.object(scraper, "_build_deep_strategy") as mock_strategy_builder:
                mock_strategy = AsyncMock()
                mock_strategy.arun = AsyncMock(return_value=empty_deep)
                mock_strategy_builder.return_value = mock_strategy

                result = await scraper.scrape_url("https://org.com")

        assert result is not None
        assert "Our Organization" in result

    @pytest.mark.asyncio
    async def test_root_failure_skips_deep_crawl(self, scraper):
        """If root scrape fails, return None without attempting deep crawl."""
        failed_root = _make_crawl_result(success=False, markdown=None, error_message="404")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=failed_root)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            with patch.object(scraper, "_build_deep_strategy") as mock_strategy_builder:
                result = await scraper.scrape_url("https://broken.com")

        assert result is None
        mock_strategy_builder.assert_not_called()
