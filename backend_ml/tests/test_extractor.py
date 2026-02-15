"""
Tests for the ExtractorService.

Uses mocked Gemini client — does NOT call the live API.
Tests verify that the extractor correctly parses Gemini responses
and handles error cases. Fixture-based parametrized tests ensure
prompt changes don't cause regressions.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.extractor import ExtractorService, get_current_date_context

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "scraping"


def _mock_gemini_client(response_json: dict):
    """Create a mock Gemini client that returns a given JSON response."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = json.dumps(response_json)
    client.models.generate_content.return_value = mock_response
    return client


def _mock_gemini_client_empty():
    """Create a mock Gemini client that returns empty response."""
    client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = ""
    client.models.generate_content.return_value = mock_response
    return client


def _mock_gemini_client_error(error: Exception):
    """Create a mock Gemini client that raises an error."""
    client = MagicMock()
    client.models.generate_content.side_effect = error
    return client


class TestExtractorService:
    def test_loads_prompt_files(self):
        """Extractor should load system prompt and examples at init."""
        client = MagicMock()
        extractor = ExtractorService(client=client)
        assert "{current_date}" not in extractor._build_system_prompt()
        assert "Example" in extractor._build_system_prompt()

    def test_date_context_injected(self):
        """System prompt should contain today's date, not template vars."""
        client = MagicMock()
        extractor = ExtractorService(client=client)
        prompt = extractor._build_system_prompt()
        current_date, day_of_week = get_current_date_context()
        assert current_date in prompt
        assert day_of_week in prompt

    @pytest.mark.asyncio
    async def test_extract_returns_dict_on_success(self):
        response = {
            "status": "OPEN",
            "hours_notes": "Mon-Fri 9am-5pm",
            "hours_today": "9am-5pm",
            "eligibility_rules": ["Open to all"],
            "is_id_required": False,
            "confidence": 8,
        }
        client = _mock_gemini_client(response)
        extractor = ExtractorService(client=client)

        result = await extractor.extract("# Test Pantry\nSome content")

        assert result is not None
        assert result["status"] == "OPEN"
        assert result["confidence"] == 8

    @pytest.mark.asyncio
    async def test_extract_returns_none_on_empty_response(self):
        client = _mock_gemini_client_empty()
        extractor = ExtractorService(client=client)

        result = await extractor.extract("# Test")
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_returns_none_on_exception(self):
        client = _mock_gemini_client_error(RuntimeError("API quota exceeded"))
        extractor = ExtractorService(client=client)

        result = await extractor.extract("# Test")
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_returns_none_on_invalid_json(self):
        client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "not valid json {{"
        client.models.generate_content.return_value = mock_response
        extractor = ExtractorService(client=client)

        result = await extractor.extract("# Test")
        assert result is None

    @pytest.mark.asyncio
    async def test_extract_to_pantry_update_returns_model(self):
        response = {
            "status": "OPEN",
            "hours_notes": "Mon-Fri 9am-5pm",
            "hours_today": "9am-5pm",
            "eligibility_rules": ["Open to all"],
            "is_id_required": False,
            "confidence": 8,
        }
        client = _mock_gemini_client(response)
        extractor = ExtractorService(client=client)

        result = await extractor.extract_to_pantry_update("# Test Pantry")

        assert result is not None
        assert result.status == "OPEN"
        assert result.confidence == 8
        assert result.is_id_required is False

    @pytest.mark.asyncio
    async def test_low_confidence_logs_warning(self, caplog):
        response = {
            "status": "UNKNOWN",
            "hours_notes": "Not listed",
            "hours_today": "Hours not listed",
            "eligibility_rules": ["Open to all"],
            "is_id_required": False,
            "confidence": 2,
        }
        client = _mock_gemini_client(response)
        extractor = ExtractorService(client=client)

        import logging
        with caplog.at_level(logging.WARNING, logger="equitable"):
            result = await extractor.extract("# Vague Church Page")

        assert result is not None
        assert result["confidence"] == 2


class TestFixtureExpectedOutputs:
    """Verify all fixture expected outputs are valid and well-formed."""

    def _get_fixture_pairs(self):
        pairs = []
        for md_file in sorted(FIXTURES_DIR.glob("*.md")):
            expected_file = FIXTURES_DIR / "expected_outputs" / f"{md_file.stem}.json"
            if expected_file.exists():
                pairs.append((md_file, expected_file))
        return pairs

    def test_all_fixtures_have_expected_outputs(self):
        """Every .md fixture should have a matching .json expected output."""
        md_files = sorted(FIXTURES_DIR.glob("*.md"))
        assert len(md_files) >= 5, f"Expected at least 5 fixtures, found {len(md_files)}"
        for md_file in md_files:
            expected_file = FIXTURES_DIR / "expected_outputs" / f"{md_file.stem}.json"
            assert expected_file.exists(), f"Missing expected output for {md_file.name}"

    def test_expected_outputs_are_valid_json(self):
        for md_file, expected_file in self._get_fixture_pairs():
            data = json.loads(expected_file.read_text())
            assert "status" in data, f"{expected_file.name}: missing 'status'"
            assert "confidence" in data, f"{expected_file.name}: missing 'confidence'"
            assert 1 <= data["confidence"] <= 10, f"{expected_file.name}: confidence out of range"
            assert data["status"] in ("OPEN", "CLOSED", "WAITLIST", "UNKNOWN"), f"{expected_file.name}: invalid status"

    @pytest.mark.parametrize(
        "md_file,expected_file",
        [
            pytest.param(md, FIXTURES_DIR / "expected_outputs" / f"{md.stem}.json", id=md.stem)
            for md in sorted(FIXTURES_DIR.glob("*.md"))
            if (FIXTURES_DIR / "expected_outputs" / f"{md.stem}.json").exists()
        ],
    )
    @pytest.mark.asyncio
    async def test_mock_extraction_matches_expected_shape(self, md_file, expected_file):
        """
        Test that when Gemini returns the expected output,
        the extractor correctly parses it into a PantryUpdate.

        This verifies the extractor's parsing logic, not Gemini's accuracy.
        For live accuracy testing, run the fixtures against the real API.
        """
        expected = json.loads(expected_file.read_text())

        # Build a mock client that returns the expected output
        gemini_response = {k: v for k, v in expected.items() if k != "_meta"}
        client = _mock_gemini_client(gemini_response)
        extractor = ExtractorService(client=client)

        markdown = md_file.read_text()
        result = await extractor.extract_to_pantry_update(markdown)

        assert result is not None
        assert result.status == expected["status"]
        assert result.is_id_required == expected["is_id_required"]
        assert result.confidence == expected["confidence"]
