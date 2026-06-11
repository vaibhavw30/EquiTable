# backend_ml/agent/nodes/curator.py
"""Curator node — quarantine chronic failures, then rank/select stale sources.

An optional `ranker` callable (the LLM path) reorders candidates and returns a
reasoning string. When `ranker` is None (or fails), we fall back to a
deterministic staleness-first ordering. Either way, selection is capped at
MAX_SOURCES_PER_RUN.
"""

import json
import logging

from agent.config import MAX_SOURCES_PER_RUN, QUARANTINE_THRESHOLD
from agent.state import ParentState

logger = logging.getLogger("equitable")


def quarantine_and_prefilter(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split candidates into (kept, quarantined) based on consecutive_failures.

    Sources with consecutive_failures > QUARANTINE_THRESHOLD are quarantined.
    """
    kept, quarantined = [], []
    for c in candidates:
        if c.get("consecutive_failures", 0) > QUARANTINE_THRESHOLD:
            quarantined.append(c)
        else:
            kept.append(c)
    return kept, quarantined


def _staleness_sort(candidates: list[dict]) -> list[dict]:
    """Sort candidates oldest-first. Sources with no last_updated sort first (oldest)."""
    return sorted(candidates, key=lambda c: (c.get("last_updated") is not None,
                                             c.get("last_updated")))


def make_curator_node(ranker=None):
    """Return a curator node.

    Args:
        ranker: Optional async callable(candidates) -> (ordered_list, reasoning).
                When None or when the ranker raises, falls back to staleness sort.
    """
    async def curator_node(state: ParentState) -> dict:
        candidates = state.get("candidate_sources", [])
        kept, quarantined = quarantine_and_prefilter(candidates)

        reasoning = "deterministic staleness ordering (no ranker / cold start)"
        ordered = _staleness_sort(kept)

        if ranker is not None and kept:
            try:
                ordered, reasoning = await ranker(kept)
            except Exception as e:  # fall back, never crash the run
                logger.warning("Curator ranker failed; using staleness fallback",
                               extra={"event": "curator_fallback", "error": str(e)})
                ordered = _staleness_sort(kept)

        selected = ordered[:MAX_SOURCES_PER_RUN]
        logger.info("Curator selected sources",
                    extra={"event": "curator_select", "selected": len(selected),
                           "quarantined": len(quarantined)})
        return {"selected_sources": selected, "quarantined": quarantined,
                "curator_reasoning": reasoning}
    return curator_node


def make_llm_ranker(chat_model):
    """Return an async ranker(candidates) -> (ordered_list, reasoning).

    `chat_model` is a LangChain chat model (curator tier). It returns JSON
    {"selected": [source_url,...], "reasoning": "..."}; we reorder candidates
    to match and append any the LLM omitted (by staleness) so nothing is lost.

    On any exception (parse error, network error, etc.) the caller (curator_node)
    catches it and falls back to staleness order.
    """
    from langchain_core.messages import HumanMessage

    async def ranker(candidates):
        summary = [
            {"source_url": c["source_url"], "city": c.get("city"),
             "hours_stale": None if not c.get("last_updated") else "stale",
             "success_rate": c.get("success_rate"),
             "consecutive_failures": c.get("consecutive_failures", 0)}
            for c in candidates
        ]
        prompt = (
            "You are a data-refresh curator. Given these food-pantry sources and "
            "their reliability metrics, return the order to refresh them this run. "
            "Prioritize staleness, reliability (higher success_rate), and city "
            "diversity. Respond ONLY with JSON: "
            '{"selected": [source_url, ...], "reasoning": "..."}\n\n'
            f"{json.dumps(summary, default=str)}"
        )
        resp = await chat_model.ainvoke([HumanMessage(content=prompt)])
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        parsed = json.loads(text)
        by_url = {c["source_url"]: c for c in candidates}
        ordered = [by_url[u] for u in parsed["selected"] if u in by_url]
        # append anything the LLM dropped, staleness-first — nothing is lost
        missing = [c for c in candidates if c["source_url"] not in parsed["selected"]]
        ordered += _staleness_sort(missing)
        return ordered, parsed.get("reasoning", "")
    return ranker
