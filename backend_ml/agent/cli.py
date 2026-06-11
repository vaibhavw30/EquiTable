"""Entrypoint for the refresh job: `python -m agent.refresh`.

Wires all real dependencies:
  - LangSmith tracing (no-op when no API key present)
  - Motor MongoDB connection (connect_to_mongo / close_mongo_connection)
  - CostTracker with the configured per-run budget
  - Real ModelFactory (Gemini via langchain_google_genai)
  - Real ScraperService (Crawl4AI)
  - LLM curator ranker
  - Extraction subgraph
  - MongoDB-backed checkpointer
  - Parent refresh graph

Do NOT call run_refresh() in tests — it hits real Gemini and real Chromium
scraping. Instead test the graph directly with FakeScraper + FakeModelFactory
(see tests/agent/test_smoke_refresh.py).
"""

import asyncio
import logging
import os
import uuid

from agent.config import MAX_COST_USD, CURATOR_MODEL, setup_langsmith
from agent.cost import CostTracker
from agent.models import ModelFactory
from agent.prompts import build_extraction_system_prompt
from agent.subgraph import build_extraction_subgraph
from agent.graph import build_refresh_graph
from agent.checkpointer import mongo_checkpointer
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.curator import make_curator_node, make_llm_ranker
from agent.nodes.metrics import make_update_metrics_node

logger = logging.getLogger("equitable")


async def run_refresh(db_name: str | None = None) -> dict:
    """Run a single refresh pass against the live database.

    Args:
        db_name: Name of the MongoDB database.  Defaults to the
                 ``DATABASE_NAME`` environment variable (fallback: ``"equitable"``).

    Returns:
        The final LangGraph state dict (includes ``results`` list, etc.).
    """
    setup_langsmith()

    if not os.getenv("GEMINI_API_KEY"):
        raise EnvironmentError("GEMINI_API_KEY is not set — cannot build LLM clients")

    from database import connect_to_mongo, close_mongo_connection
    from services.scraper import get_scraper_service

    await connect_to_mongo()

    run_id = str(uuid.uuid4())
    logger.info("Refresh starting", extra={"event": "refresh_start", "run_id": run_id})
    cost_tracker = CostTracker(budget_usd=MAX_COST_USD)

    # Curator ranker — cheapest Gemini tier for ranking, not extraction
    from langchain_google_genai import ChatGoogleGenerativeAI
    curator_chat = ChatGoogleGenerativeAI(
        model=CURATOR_MODEL,
        temperature=0,
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )

    try:
        subgraph = build_extraction_subgraph(
            scraper=get_scraper_service(),
            model_factory=ModelFactory(),
            cost_tracker=cost_tracker,
            system_prompt_builder=build_extraction_system_prompt,
        )

        resolved_db_name = db_name or os.getenv("DATABASE_NAME", "equitable")

        async with mongo_checkpointer(db_name=resolved_db_name) as cp:
            app = build_refresh_graph(
                load_node=make_load_sources_node(),
                curator_node=make_curator_node(ranker=make_llm_ranker(curator_chat)),
                subgraph=subgraph,
                cost_tracker=cost_tracker,
                update_metrics_node=make_update_metrics_node(),
                checkpointer=cp,
            )
            final = await app.ainvoke(
                {"run_id": run_id, "cost_budget_usd": MAX_COST_USD},
                {"configurable": {"thread_id": run_id}},
            )
    except Exception:
        logger.exception("Refresh run failed", extra={"event": "refresh_error", "run_id": run_id})
        raise
    finally:
        await close_mongo_connection()

    results = final.get("results", [])
    succeeded = sum(1 for r in results if r.get("outcome") == "success")
    failed = sum(1 for r in results if r.get("outcome") == "failed")
    skipped = sum(1 for r in results if r.get("outcome") == "skipped_budget")
    logger.info(
        "Refresh complete",
        extra={
            "event": "refresh_done",
            "run_id": run_id,
            "processed": len(results),
            "succeeded": succeeded,
            "failed": failed,
            "skipped_budget": skipped,
            "cost_spent_usd": round(final.get("cost_spent_usd", 0.0), 4),
        },
    )
    return final


def main() -> None:
    """Synchronous entry point — used by `python -m agent.refresh`."""
    logging.basicConfig(level=logging.INFO)
    try:
        final = asyncio.run(run_refresh())
    except Exception:
        logger.exception("Refresh run failed", extra={"event": "refresh_error"})
        raise SystemExit(1)
    results = final.get("results", [])
    failed = sum(1 for r in results if r.get("outcome") == "failed")
    if results and failed == len(results):
        logger.error("All sources failed", extra={"event": "refresh_all_failed", "failed": failed})
        raise SystemExit(2)


if __name__ == "__main__":
    main()
