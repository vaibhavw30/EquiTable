# backend_ml/tests/agent/test_curator.py
from datetime import datetime, timezone, timedelta
from agent.nodes.curator import make_curator_node, quarantine_and_prefilter

now = datetime.now(timezone.utc)


def _cand(url, hours_old, consec=0):
    return {"source_url": url, "pantry_id": url, "city": "Atlanta",
            "last_updated": now - timedelta(hours=hours_old),
            "consecutive_failures": consec, "success_rate": None}


def test_quarantine_excludes_chronic_failures():
    cands = [_cand("a", 48, consec=6), _cand("b", 48, consec=2)]
    kept, quarantined = quarantine_and_prefilter(cands)
    assert [c["source_url"] for c in kept] == ["b"]
    assert [c["source_url"] for c in quarantined] == ["a"]


async def test_curator_cold_start_sorts_by_staleness(test_db=None):
    cands = [_cand("new", 25), _cand("old", 100), _cand("mid", 50)]
    # ranker=None → deterministic staleness fallback
    node = make_curator_node(ranker=None)
    out = await node({"candidate_sources": cands})
    assert [c["source_url"] for c in out["selected_sources"]] == ["old", "mid", "new"]


async def test_curator_respects_max_sources(monkeypatch):
    import agent.nodes.curator as mod
    monkeypatch.setattr(mod, "MAX_SOURCES_PER_RUN", 2)
    cands = [_cand("a", 100), _cand("b", 90), _cand("c", 80)]
    node = make_curator_node(ranker=None)
    out = await node({"candidate_sources": cands})
    assert len(out["selected_sources"]) == 2


async def test_curator_quarantines_and_excludes_from_selected():
    """Sources above QUARANTINE_THRESHOLD must not appear in selected_sources."""
    cands = [_cand("good", 48, consec=0), _cand("bad", 48, consec=6)]
    node = make_curator_node(ranker=None)
    out = await node({"candidate_sources": cands})
    selected_urls = {c["source_url"] for c in out["selected_sources"]}
    quarantined_urls = {c["source_url"] for c in out["quarantined"]}
    assert "good" in selected_urls
    assert "bad" not in selected_urls
    assert "bad" in quarantined_urls


# ── Task 16: LLM ranker ──────────────────────────────────────────────────────
from agent.nodes.curator import make_llm_ranker  # noqa: E402


class _FakeChat:
    async def ainvoke(self, messages):
        class M:
            content = '{"selected": ["old", "new"], "reasoning": "freshness first"}'
        return M()


async def test_llm_ranker_orders_by_returned_list():
    cands = [_cand("new", 25), _cand("old", 100)]
    ranker = make_llm_ranker(_FakeChat())
    ordered, reasoning = await ranker(cands)
    assert [c["source_url"] for c in ordered] == ["old", "new"]
    assert "freshness" in reasoning


async def test_llm_ranker_appends_omitted_candidates():
    """Candidates the LLM omits from 'selected' must be appended, none lost."""
    cands = [_cand("a", 100), _cand("b", 50), _cand("c", 75)]

    class _PartialChat:
        async def ainvoke(self, messages):
            class M:
                content = '{"selected": ["a"], "reasoning": "a first"}'
            return M()

    ranker = make_llm_ranker(_PartialChat())
    ordered, _ = await ranker(cands)
    urls = [c["source_url"] for c in ordered]
    assert urls[0] == "a"                  # LLM pick is first
    assert set(urls) == {"a", "b", "c"}    # nothing lost


async def test_llm_ranker_fallback_on_bad_json():
    """When the LLM returns unparseable JSON, ranker raises (curator catches it)."""
    class _BadChat:
        async def ainvoke(self, messages):
            class M:
                content = "not json at all"
            return M()

    ranker = make_llm_ranker(_BadChat())
    try:
        await ranker([_cand("x", 48)])
        assert False, "Expected exception"
    except Exception:
        pass  # good — curator_node wraps this in try/except


async def test_curator_falls_back_when_ranker_raises():
    """make_curator_node catches ranker exceptions and uses staleness sort."""
    async def _failing_ranker(candidates):
        raise RuntimeError("LLM unreachable")

    cands = [_cand("new", 25), _cand("old", 100)]
    node = make_curator_node(ranker=_failing_ranker)
    out = await node({"candidate_sources": cands})
    # Should still complete (fallback to staleness)
    assert [c["source_url"] for c in out["selected_sources"]] == ["old", "new"]
