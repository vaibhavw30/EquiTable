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
