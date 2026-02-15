"""
Tests for the post-extraction validation rules.
Every business rule in validator.py gets an explicit test.
"""

import pytest
from datetime import datetime, timezone, timedelta

from services.validator import validate_extraction, ValidationError


def _valid_data(**overrides):
    """Return a valid extraction dict, with optional overrides."""
    base = {
        "status": "OPEN",
        "hours_notes": "Mon-Fri 9am-5pm",
        "hours_today": "9am-5pm",
        "eligibility_rules": ["Open to all"],
        "is_id_required": False,
        "residency_req": None,
        "special_notes": None,
        "confidence": 8,
    }
    base.update(overrides)
    return base


class TestConfidenceValidation:
    def test_confidence_below_1_rejected(self):
        with pytest.raises(ValidationError, match="confidence"):
            validate_extraction(_valid_data(confidence=0))

    def test_confidence_above_10_rejected(self):
        with pytest.raises(ValidationError, match="confidence"):
            validate_extraction(_valid_data(confidence=11))

    def test_confidence_null_rejected(self):
        with pytest.raises(ValidationError, match="confidence"):
            validate_extraction(_valid_data(confidence=None))

    def test_confidence_non_integer_rejected(self):
        with pytest.raises(ValidationError, match="confidence"):
            validate_extraction(_valid_data(confidence=7.5))

    def test_confidence_1_accepted(self):
        result = validate_extraction(_valid_data(confidence=1))
        assert result["confidence"] == 1

    def test_confidence_10_accepted(self):
        result = validate_extraction(_valid_data(confidence=10))
        assert result["confidence"] == 10


class TestStatusValidation:
    def test_valid_statuses_accepted(self):
        for status in ["OPEN", "CLOSED", "WAITLIST", "UNKNOWN"]:
            result = validate_extraction(_valid_data(status=status))
            assert result["status"] == status

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError, match="status"):
            validate_extraction(_valid_data(status="MAYBE"))

    def test_null_status_rejected(self):
        with pytest.raises(ValidationError, match="status"):
            validate_extraction(_valid_data(status=None))

    def test_lowercase_status_rejected(self):
        with pytest.raises(ValidationError, match="status"):
            validate_extraction(_valid_data(status="open"))


class TestNameValidation:
    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            validate_extraction(_valid_data(name=""))

    def test_whitespace_name_rejected(self):
        with pytest.raises(ValidationError, match="name"):
            validate_extraction(_valid_data(name="   "))

    def test_valid_name_accepted(self):
        result = validate_extraction(_valid_data(name="Test Pantry"))
        assert result["name"] == "Test Pantry"

    def test_name_absent_is_ok(self):
        """Extraction dicts may not include name (it comes from the DB record)."""
        data = _valid_data()
        assert "name" not in data
        result = validate_extraction(data)
        assert result is not None


class TestEligibilityRulesValidation:
    def test_non_list_rejected(self):
        with pytest.raises(ValidationError, match="eligibility_rules"):
            validate_extraction(_valid_data(eligibility_rules="Open to all"))

    def test_list_accepted(self):
        result = validate_extraction(
            _valid_data(eligibility_rules=["ID required", "Fulton County only"])
        )
        assert len(result["eligibility_rules"]) == 2

    def test_empty_list_accepted(self):
        result = validate_extraction(_valid_data(eligibility_rules=[]))
        assert result["eligibility_rules"] == []


class TestLastUpdatedValidation:
    def test_future_timestamp_rejected(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        with pytest.raises(ValidationError, match="last_updated"):
            validate_extraction(_valid_data(last_updated=future))

    def test_past_timestamp_accepted(self):
        past = "2025-01-01T00:00:00Z"
        result = validate_extraction(_valid_data(last_updated=past))
        assert result["last_updated"] == past

    def test_absent_timestamp_ok(self):
        """last_updated is optional in extraction output."""
        data = _valid_data()
        assert "last_updated" not in data
        result = validate_extraction(data)
        assert result is not None

    def test_invalid_timestamp_format_rejected(self):
        with pytest.raises(ValidationError, match="last_updated"):
            validate_extraction(_valid_data(last_updated="not-a-date"))


class TestIsIdRequiredValidation:
    def test_boolean_accepted(self):
        result = validate_extraction(_valid_data(is_id_required=True))
        assert result["is_id_required"] is True

    def test_non_boolean_rejected(self):
        with pytest.raises(ValidationError, match="is_id_required"):
            validate_extraction(_valid_data(is_id_required="yes"))

    def test_null_accepted(self):
        result = validate_extraction(_valid_data(is_id_required=None))
        assert result["is_id_required"] is None


class TestValidDataPassesAll:
    def test_fully_valid_data_passes(self):
        data = _valid_data()
        result = validate_extraction(data)
        assert result["confidence"] == 8
        assert result["status"] == "OPEN"

    def test_all_fields_populated_passes(self):
        data = _valid_data(
            name="Community Pantry",
            residency_req="Fulton County",
            special_notes="Closed Thanksgiving week",
            last_updated="2025-06-15T12:00:00Z",
        )
        result = validate_extraction(data)
        assert result["name"] == "Community Pantry"
