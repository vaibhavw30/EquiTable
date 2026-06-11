# backend_ml/agent/subgraph.py
"""Assemble the per-source extraction subgraph:

    scrape → extract → validate → should_retry? ─ retry → bump_retry → extract
                                                └ done  → persist → END
"""

from langgraph.graph import StateGraph, START, END
from agent.state import ExtractionState
from agent.nodes.scrape import make_scrape_node
from agent.nodes.extract import make_extract_node
from agent.nodes.validate import validate_node, should_retry, bump_retry
from agent.nodes.persist import make_persist_node


def build_extraction_subgraph(scraper, model_factory, cost_tracker,
                              system_prompt_builder, db=None):
    g = StateGraph(ExtractionState)
    g.add_node("scrape", make_scrape_node(scraper))
    g.add_node("extract", make_extract_node(model_factory, cost_tracker, system_prompt_builder))
    g.add_node("validate", validate_node)
    g.add_node("bump_retry", bump_retry)
    g.add_node("persist", make_persist_node(db=db))

    g.add_edge(START, "scrape")
    g.add_edge("scrape", "extract")
    g.add_edge("extract", "validate")
    g.add_conditional_edges("validate", should_retry,
                            {"retry": "bump_retry", "done": "persist"})
    g.add_edge("bump_retry", "extract")
    g.add_edge("persist", END)
    return g.compile()
