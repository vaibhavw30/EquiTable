"""
Tests for the ScraperService.
All tests use mocked Crawl4AI — no live HTTP calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.scraper import ScraperService


def _make_crawl_result(success=True, markdown="# Test\nSome content here", error_message=None):
    """Build a mock CrawlResult."""
    result = MagicMock()
    result.success = success
    result.markdown = markdown
    result.markdown_v2 = None
    result.error_message = error_message
    return result


class TestScraperService:
    @pytest.fixture
    def scraper(self):
        return ScraperService()

    @pytest.mark.asyncio
    async def test_returns_markdown_on_success(self, scraper):
        mock_result = _make_crawl_result(markdown="# Food Pantry\nOpen Mon-Fri 9am-5pm")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=mock_result)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            result = await scraper.scrape_url("https://example.com/pantry")

        assert result is not None
        assert "Food Pantry" in result

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self, scraper):
        mock_result = _make_crawl_result(success=False, markdown=None, error_message="Connection refused")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=mock_result)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            result = await scraper.scrape_url("https://down-site.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_empty_content(self, scraper):
        mock_result = _make_crawl_result(markdown="")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=mock_result)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            result = await scraper.scrape_url("https://empty-site.com")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_minimal_content(self, scraper):
        """Content under 20 chars is treated as empty."""
        mock_result = _make_crawl_result(markdown="hi")

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=mock_result)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

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
        mock_v2.raw_markdown = "# Better Markdown\nClean content from v2"
        mock_result.markdown_v2 = mock_v2

        with patch("services.scraper.AsyncWebCrawler") as MockCrawler:
            instance = AsyncMock()
            instance.arun = AsyncMock(return_value=mock_result)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockCrawler.return_value = instance

            result = await scraper.scrape_url("https://example.com")

        assert result == "# Better Markdown\nClean content from v2"
