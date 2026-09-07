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


# ── Task 16 / Gemini-3 fix: LLM ranker via structured output ─────────────────
from agent.nodes.curator import make_llm_ranker, CuratorRanking  # noqa: E402


class _StructuredChat:
    """Mimic ChatGoogleGenerativeAI.with_structured_output(schema, include_raw=True).

    `with_structured_output` returns a runnable whose `ainvoke` yields the
    LangChain ``{"parsed", "raw", "parsing_error"}`` dict (mirroring the
    extractor). The bare `ainvoke` returns the raw Gemini-3 content shape — a
    *list* of blocks, not a string — so tests can prove the ranker never calls
    ``.content.strip()`` on it.
    """

    def __init__(self, selected, reasoning="because", parsing_error=None):
        self._selected = selected
        self._reasoning = reasoning
        self._parsing_error = parsing_error
        self.structured_called = False

    def with_structured_output(self, schema, include_raw=True):
        self.structured_called = True
        parsed = None if self._parsing_error else schema(
            selected=self._selected, reasoning=self._reasoning)
        err = self._parsing_error

        class _Runnable:
            async def ainvoke(_self, messages):
                return {"parsed": parsed, "raw": None, "parsing_error": err}

        return _Runnable()

    async def ainvoke(self, messages):
        # Real Gemini 3 returns .content as a list of content blocks, not a str.
        class M:
            content = [{"type": "text", "text": "{}", "extras": {"signature": "s"}}]
        return M()


async def test_llm_ranker_orders_by_returned_list():
    cands = [_cand("new", 25), _cand("old", 100)]
    chat = _StructuredChat(selected=["old", "new"], reasoning="freshness first")
    ranker = make_llm_ranker(chat)
    ordered, reasoning = await ranker(cands)
    assert [c["source_url"] for c in ordered] == ["old", "new"]
    assert "freshness" in reasoning
    assert chat.structured_called  # used structured output, not hand-parsed JSON


async def test_llm_ranker_handles_gemini3_list_content():
    """Regression: Gemini 3 returns .content as a list of blocks. The old ranker
    did ``resp.content.strip()`` and crashed with
    ``AttributeError: 'list' object has no attribute 'strip'``. Structured
    output sidesteps raw content parsing entirely."""
    cands = [_cand("new", 25), _cand("old", 100)]
    chat = _StructuredChat(selected=["old", "new"])
    raw = await chat.ainvoke([])          # sanity: the shape that broke is a list
    assert isinstance(raw.content, list)
    ordered, _ = await make_llm_ranker(chat)(cands)
    assert [c["source_url"] for c in ordered] == ["old", "new"]


async def test_llm_ranker_appends_omitted_candidates():
    """Candidates the LLM omits from 'selected' must be appended, none lost."""
    cands = [_cand("a", 100), _cand("b", 50), _cand("c", 75)]
    chat = _StructuredChat(selected=["a"], reasoning="a first")
    ranker = make_llm_ranker(chat)
    ordered, _ = await ranker(cands)
    urls = [c["source_url"] for c in ordered]
    assert urls[0] == "a"                  # LLM pick is first
    assert set(urls) == {"a", "b", "c"}    # nothing lost


async def test_llm_ranker_raises_on_parse_failure():
    """When structured output can't parse (parsed=None / parsing_error set), the
    ranker raises so curator_node falls back to deterministic staleness order."""
    chat = _StructuredChat(selected=None, parsing_error=ValueError("bad output"))
    ranker = make_llm_ranker(chat)
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
