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
