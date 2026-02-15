"""
Validator Service - Post-extraction validation rules for pantry data.

Catches bad LLM extractions before they reach the database.
"""

import logging
from datetime import datetime, timezone

from models.pantry import PantryStatus

logger = logging.getLogger("equitable")

VALID_STATUSES = {s.value for s in PantryStatus}


class ValidationError(Exception):
    """Raised when extracted data fails validation rules."""

    def __init__(self, field: str, reason: str, value=None):
        self.field = field
        self.reason = reason
        self.value = value
        super().__init__(f"Validation failed on '{field}': {reason}")


def validate_extraction(data: dict) -> dict:
    """
    Validate a raw extraction dict against business rules.

    Args:
        data: Raw dict from LLM extraction.

    Returns:
        The same dict if valid.

    Raises:
        ValidationError: If any field fails validation.
    """
    _validate_confidence(data)
    _validate_status(data)
    _validate_name(data)
    _validate_eligibility_rules(data)
    _validate_last_updated(data)
    _validate_is_id_required(data)

    return data


def _validate_confidence(data: dict):
    confidence = data.get("confidence")
    if confidence is None:
        raise ValidationError("confidence", "must not be null")
    if not isinstance(confidence, int):
        raise ValidationError("confidence", "must be an integer", confidence)
    if confidence < 1 or confidence > 10:
        raise ValidationError(
            "confidence", f"must be 1-10, got {confidence}", confidence
        )


def _validate_status(data: dict):
    status = data.get("status")
    if status is None:
        raise ValidationError("status", "must not be null")
    if status not in VALID_STATUSES:
        raise ValidationError(
            "status", f"must be one of {VALID_STATUSES}, got '{status}'", status
        )


def _validate_name(data: dict):
    """Name is only validated when present in the extraction (not all extractions include name)."""
    name = data.get("name")
    if name is not None and (not isinstance(name, str) or name.strip() == ""):
        raise ValidationError("name", "must be a non-empty string", name)


def _validate_eligibility_rules(data: dict):
    rules = data.get("eligibility_rules")
    if rules is not None:
        if not isinstance(rules, list):
            raise ValidationError(
                "eligibility_rules", "must be a list", rules
            )


def _validate_last_updated(data: dict):
    """If last_updated is present, it must not be in the future."""
    last_updated = data.get("last_updated")
    if last_updated is None:
        return
    if isinstance(last_updated, str):
        try:
            last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        except ValueError:
            raise ValidationError(
                "last_updated", "must be a valid ISO 8601 timestamp", last_updated
            )
    if isinstance(last_updated, datetime):
        now = datetime.now(timezone.utc)
        if last_updated.tzinfo is None:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        if last_updated > now:
            raise ValidationError(
                "last_updated", "must not be in the future", last_updated
            )


def _validate_is_id_required(data: dict):
    val = data.get("is_id_required")
    if val is not None and not isinstance(val, bool):
        raise ValidationError(
            "is_id_required", "must be a boolean", val
        )
