"""Validate node + retry/escalation edge logic.

Reuses services/validator.validate_extraction so validation rules are not
duplicated. When extracted_data is None (parse failure from extract node),
`or {}` coerces it to an empty dict so validate_extraction raises on missing
confidence — causing should_retry to fire and escalate.
"""

from agent.config import CONFIDENCE_THRESHOLD, MAX_RETRIES
from agent.state import ExtractionState
from services.validator import validate_extraction, ValidationError


async def validate_node(state: ExtractionState) -> dict:
    data = state.get("extracted_data") or {}
    try:
        validate_extraction(data)
        return {"validation_errors": []}
    except ValidationError as e:
        return {"validation_errors": [f"{e.field}: {e.reason}"]}


def should_retry(state: ExtractionState) -> str:
    has_errors = bool(state.get("validation_errors"))
    # confidence is None only when extraction produced no data; in that case
    # validate_node has already set validation_errors, so has_errors fires the
    # retry. The `or 0` is belt-and-suspenders for future validator relaxation.
    low_conf = (state.get("confidence") or 0) < CONFIDENCE_THRESHOLD
    if (has_errors or low_conf) and state.get("retry_count", 0) < MAX_RETRIES:
        return "retry"
    return "done"


def bump_retry(state: ExtractionState) -> dict:
    new_count = state.get("retry_count", 0) + 1
    return {"retry_count": new_count, "model_tier": new_count}
