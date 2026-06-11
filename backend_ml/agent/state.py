"""Typed state for the refresh agent graphs."""

from typing import Literal, Optional, TypedDict
from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """Structured-output schema for Gemini extraction (mirrors RESPONSE_SCHEMA)."""
    status: Literal["OPEN", "CLOSED", "WAITLIST", "UNKNOWN"]
    hours_notes: str
    hours_today: str
    eligibility_rules: list[str]
    is_id_required: bool
    residency_req: Optional[str] = None
    special_notes: Optional[str] = None
    confidence: int = Field(description="1-10")


class ExtractionState(TypedDict, total=False):
    """State threaded through the per-source extraction subgraph."""
    source_url: str
    pantry_id: str
    raw_markdown: Optional[str]
    extracted_data: Optional[dict]
    validation_errors: list[str]
    confidence: Optional[int]
    retry_count: int
    model_tier: int
    latency_ms: float
    outcome: Literal["success", "failed", "skipped_budget"]
    final_update: Optional[dict]


class ParentState(TypedDict, total=False):
    """State for the top-level refresh graph."""
    run_id: str
    candidate_sources: list[dict]
    selected_sources: list[dict]      # subset of candidates the curator chose
    curator_reasoning: str
    quarantined: list[dict]
    results: list[dict]               # one summary dict per processed source
    cost_spent_usd: float
    cost_budget_usd: float
