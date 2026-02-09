"""
Scraper Service - Uses Firecrawl to extract main content from pantry websites
"""

import os
from typing import Optional
from firecrawl import FirecrawlApp
from dotenv import load_dotenv

load_dotenv()


class ScraperService:
    """
    Service for scraping pantry websites using Firecrawl.
    Extracts main content as Markdown for further processing.
    """

    def __init__(self):
        """
        Initialize the Firecrawl client with API key from environment.

        Raises:
            ValueError: If FIRECRAWL_KEY is not set in .env.
        """
        api_key = os.getenv("FIRECRAWL_KEY")
        if not api_key:
            raise ValueError("FIRECRAWL_KEY not found in .env")

        self.app = FirecrawlApp(api_key=api_key)

    def scrape_url(self, url: str) -> Optional[str]:
        """
        Scrape a URL and return its main content as Markdown.

        Uses Firecrawl with onlyMainContent to avoid nav menus and footers.

        Args:
            url: The URL to scrape.

        Returns:
            The markdown content of the page, or None if scraping fails.
        """
        try:
            result = self.app.scrape(
                url,
                formats=["markdown"],
            )

            # Result is a Document object with a markdown attribute
            if result and hasattr(result, "markdown") and result.markdown:
                # Check for error pages (404, etc.)
                if hasattr(result, "metadata") and result.metadata:
                    status_code = getattr(result.metadata, "status_code", 200)
                    if status_code and status_code >= 400:
                        print(f"Failed to scrape {url}: HTTP {status_code}")
                        return None

                return result.markdown

            print(f"Failed to scrape {url}: No markdown content in response")
            return None

        except Exception as e:
            print(f"Failed to scrape {url}: {e}")
            return None

    # Async wrapper for use in FastAPI endpoints
    async def scrape_pantry_website(self, url: str) -> Optional[str]:
        """Async-compatible wrapper around scrape_url."""
        return self.scrape_url(url)


# Singleton instance for reuse
_scraper_instance: Optional[ScraperService] = None


def get_scraper_service() -> ScraperService:
    """Get or create a singleton ScraperService instance."""
    global _scraper_instance
    if _scraper_instance is None:
        _scraper_instance = ScraperService()
    return _scraper_instance
