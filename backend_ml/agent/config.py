"""Tunable configuration for the refresh agent.

All knobs live here so behavior is adjustable without touching graph logic.
Pricing values are USD per 1,000,000 tokens — VERIFY against current Gemini
pricing before relying on cost numbers; they drift over time.
"""

import os

# ── Refresh-run knobs ─────────────────────────────────────────────────────
FRESHNESS_FLOOR_HOURS: int = 24      # only pantries staler than this are candidates
MAX_SOURCES_PER_RUN: int = 25        # curator selects at most this many per run
MAX_CONCURRENT: int = 4              # concurrent extraction subgraphs
CONFIDENCE_THRESHOLD: int = 6        # confidence below this triggers a retry
MAX_RETRIES: int = 2                 # retries after the initial attempt (3 attempts total)
QUARANTINE_THRESHOLD: int = 5        # consecutive_failures above this → skip + report
MAX_COST_USD: float = 0.50           # per-run dollar budget

# ── Model ladder (cheap-first with escalation) ────────────────────────────
# Index 0 = initial attempt, escalating per retry. The last rung is reused
# if retries exceed the ladder length.
EXTRACTION_MODEL_LADDER: list[str] = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]
CURATOR_MODEL: str = "gemini-2.0-flash-lite"

# ── Pricing: model -> (input_per_1M, output_per_1M) in USD ────────────────
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}


def model_for_tier(tier: int) -> str:
    """Return the model name for an escalation tier (clamped to the ladder)."""
    idx = max(0, min(tier, len(EXTRACTION_MODEL_LADDER) - 1))
    return EXTRACTION_MODEL_LADDER[idx]


def setup_langsmith() -> None:
    """Enable LangSmith tracing if an API key is present (no-op otherwise)."""
    if os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", "equitable-refresh-agent")
