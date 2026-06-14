"""LangGraph Studio entrypoint.

Builds the refresh agent's parent graph with production dependencies so it can
be visualized and run interactively via `langgraph dev` (LangGraph Studio).

Notes:
- Studio doesn't run the FastAPI startup lifespan, so we create an explicit
  Motor DB handle here and inject it into the DB-touching nodes (rather than
  relying on the `database.db` global). Motor is lazy, so the graph constructs
  fine even if Mongo is unreachable — handy for pure visualization.
- Studio supplies its own persistence layer, so no checkpointer is wired here.
- Requires `.env`: MONGO_URI (+ DATABASE_NAME), GEMINI_API_KEY; optionally
  JINA_API_KEY / LANGCHAIN_API_KEY.
"""

import os

from motor.motor_asyncio import AsyncIOMotorClient

from database import _mongo_client_kwargs, MONGO_URI, DATABASE_NAME
from agent.config import CURATOR_MODEL, MAX_COST_USD
from agent.cost import CostTracker
from agent.models import ModelFactory
from agent.prompts import build_extraction_system_prompt
from agent.subgraph import build_extraction_subgraph
from agent.graph import build_refresh_graph
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.curator import make_curator_node, make_llm_ranker
from agent.nodes.metrics import make_update_metrics_node
from services.scraper import get_scraper_service


def make_graph():
    """Factory invoked by LangGraph Studio (`langgraph.json`)."""
    db = AsyncIOMotorClient(MONGO_URI, **_mongo_client_kwargs())[DATABASE_NAME]
    tracker = CostTracker(budget_usd=MAX_COST_USD)

    subgraph = build_extraction_subgraph(
        scraper=get_scraper_service(),
        model_factory=ModelFactory(),
        cost_tracker=tracker,
        system_prompt_builder=build_extraction_system_prompt,
        db=db,
    )

    from langchain_google_genai import ChatGoogleGenerativeAI
    curator_chat = ChatGoogleGenerativeAI(
        model=CURATOR_MODEL, temperature=0, google_api_key=os.getenv("GEMINI_API_KEY")
    )

    return build_refresh_graph(
        load_node=make_load_sources_node(db=db),
        curator_node=make_curator_node(ranker=make_llm_ranker(curator_chat)),
        subgraph=subgraph,
        cost_tracker=tracker,
        update_metrics_node=make_update_metrics_node(db=db),
        checkpointer=None,
    )
