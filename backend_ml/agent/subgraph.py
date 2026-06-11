# backend_ml/agent/subgraph.py
"""Assemble the per-source extraction subgraph:

    scrape → (scrape ok?) ─ yes → extract → validate → should_retry? ─ retry → bump_retry → extract
                           └ no  → END                                └ done  → persist → END

A failed scrape (raw_markdown=None) short-circuits directly to END with
outcome="failed" already set by scrape_node — no LLM call, no DB write.
"""

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph
from agent.state import ExtractionState
from agent.nodes.scrape import make_scrape_node
from agent.nodes.extract import make_extract_node
from agent.nodes.validate import validate_node, should_retry, bump_retry
from agent.nodes.persist import make_persist_node


def build_extraction_subgraph(scraper, model_factory, cost_tracker,
                              system_prompt_builder, db=None) -> CompiledStateGraph:
    """Build and compile the per-source extraction subgraph.

    Returns a compiled LangGraph (CompiledStateGraph) that:
    - Scrapes the source URL; short-circuits to END on failure (no LLM call).
    - Extracts structured data via the model_factory with tier escalation.
    - Validates the extraction and retries up to MAX_RETRIES times.
    - Persists the result to MongoDB via the persist node.

    Args:
        scraper: ScraperService-compatible object with scrape_url(url) -> str | None.
        model_factory: Factory with .get(tier) -> structured model and .name_for_tier(tier).
        cost_tracker: CostTracker instance tracking USD spent this run.
        system_prompt_builder: Callable returning the system prompt string.
        db: AsyncIOMotorDatabase instance (or None to skip persistence).
    """
    g = StateGraph(ExtractionState)
    g.add_node("scrape", make_scrape_node(scraper))
    g.add_node("extract", make_extract_node(model_factory, cost_tracker, system_prompt_builder))
    g.add_node("validate", validate_node)
    g.add_node("bump_retry", bump_retry)
    g.add_node("persist", make_persist_node(db=db))

    g.add_edge(START, "scrape")
    g.add_conditional_edges(
        "scrape",
        lambda state: "extract" if state.get("raw_markdown") else "skip",
        {"extract": "extract", "skip": END},
    )
    g.add_edge("extract", "validate")
    g.add_conditional_edges("validate", should_retry,
                            {"retry": "bump_retry", "done": "persist"})
    g.add_edge("bump_retry", "extract")
    g.add_edge("persist", END)
    return g.compile()
