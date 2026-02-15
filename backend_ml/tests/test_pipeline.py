"""
Tests for the IngestionPipeline.

All tests use mocked scraper and extractor — no live HTTP or API calls.
Tests verify end-to-end orchestration logic, error propagation, and logging.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from services.ingestion_pipeline import IngestionPipeline, IngestionError
from services.scraper import ScraperService
from services.extractor import ExtractorService

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "scraping"


def _make_pipeline(scrape_return=None, extract_return=None):
    """Create a pipeline with mocked scraper and extractor."""
    scraper = MagicMock(spec=ScraperService)
    scraper.scrape_url = AsyncMock(return_value=scrape_return)

    extractor = MagicMock(spec=ExtractorService)
    extractor.extract = AsyncMock(return_value=extract_return)

    return IngestionPipeline(scraper=scraper, extractor=extractor)


def _valid_extraction():
    """Return a valid extraction dict."""
    return {
        "status": "OPEN",
        "hours_notes": "Mon-Fri 9am-5pm",
        "hours_today": "9am-5pm",
        "eligibility_rules": ["Open to all"],
        "is_id_required": False,
        "confidence": 8,
    }


class TestIngestionPipeline:
    @pytest.mark.asyncio
    async def test_happy_path_returns_pantry_update(self):
        """Full pipeline should return a valid PantryUpdate."""
        pipeline = _make_pipeline(
            scrape_return="# Test Pantry\nOpen Mon-Fri",
            extract_return=_valid_extraction(),
        )

        result = await pipeline.ingest("https://example.com/pantry")

        assert result is not None
        assert result.status == "OPEN"
        assert result.confidence == 8
        assert result.is_id_required is False

    @pytest.mark.asyncio
    async def test_scrape_failure_raises_ingestion_error(self):
        """Pipeline should raise IngestionError when scraper returns None."""
        pipeline = _make_pipeline(scrape_return=None)

        with pytest.raises(IngestionError) as exc_info:
            await pipeline.ingest("https://down-site.com")

        assert exc_info.value.stage == "scrape"
        assert "no content" in exc_info.value.reason.lower()

    @pytest.mark.asyncio
    async def test_extraction_failure_raises_ingestion_error(self):
        """Pipeline should raise IngestionError when extractor returns None."""
        pipeline = _make_pipeline(
            scrape_return="# Some markdown content here",
            extract_return=None,
        )

        with pytest.raises(IngestionError) as exc_info:
            await pipeline.ingest("https://example.com")

        assert exc_info.value.stage == "extract"
        assert "no data" in exc_info.value.reason.lower()

    @pytest.mark.asyncio
    async def test_validation_failure_raises_ingestion_error(self):
        """Pipeline should raise IngestionError when validation fails."""
        bad_data = _valid_extraction()
        bad_data["confidence"] = 99  # out of range

        pipeline = _make_pipeline(
            scrape_return="# Test Pantry",
            extract_return=bad_data,
        )

        with pytest.raises(IngestionError) as exc_info:
            await pipeline.ingest("https://example.com")

        assert exc_info.value.stage == "validate"
        assert "confidence" in exc_info.value.reason.lower()

    @pytest.mark.asyncio
    async def test_invalid_status_fails_validation(self):
        """Pipeline should reject invalid status values."""
        bad_data = _valid_extraction()
        bad_data["status"] = "MAYBE"

        pipeline = _make_pipeline(
            scrape_return="# Test Pantry",
            extract_return=bad_data,
        )

        with pytest.raises(IngestionError) as exc_info:
            await pipeline.ingest("https://example.com")

        assert exc_info.value.stage == "validate"
        assert "status" in exc_info.value.reason.lower()

    @pytest.mark.asyncio
    async def test_low_confidence_still_succeeds(self):
        """Low confidence extractions should pass (validator allows 1-10)."""
        data = _valid_extraction()
        data["confidence"] = 2
        data["status"] = "UNKNOWN"

        pipeline = _make_pipeline(
            scrape_return="# Vague Church Page",
            extract_return=data,
        )

        result = await pipeline.ingest("https://example.com")

        assert result is not None
        assert result.confidence == 2
        assert result.status == "UNKNOWN"

    @pytest.mark.asyncio
    async def test_ingestion_logs_start_and_complete(self, caplog):
        """Pipeline should log ingestion_start and ingestion_complete events."""
        import logging

        pipeline = _make_pipeline(
            scrape_return="# Test Pantry\nContent",
            extract_return=_valid_extraction(),
        )

        with caplog.at_level(logging.INFO, logger="equitable"):
            await pipeline.ingest("https://example.com")

        messages = [r.message for r in caplog.records]
        assert any("started" in m.lower() for m in messages)
        assert any("complete" in m.lower() for m in messages)

    @pytest.mark.asyncio
    async def test_url_propagated_to_error(self):
        """IngestionError should carry the original URL."""
        pipeline = _make_pipeline(scrape_return=None)

        with pytest.raises(IngestionError) as exc_info:
            await pipeline.ingest("https://specific-url.com/pantry")

        assert exc_info.value.url == "https://specific-url.com/pantry"


class TestPipelineWithFixtures:
    """Test pipeline with real fixture data (mocked scraper + extractor)."""

    def _get_fixture_pairs(self):
        pairs = []
        for md_file in sorted(FIXTURES_DIR.glob("*.md")):
            expected_file = FIXTURES_DIR / "expected_outputs" / f"{md_file.stem}.json"
            if expected_file.exists():
                pairs.append((md_file, expected_file))
        return pairs

    @pytest.mark.parametrize(
        "md_file,expected_file",
        [
            pytest.param(md, FIXTURES_DIR / "expected_outputs" / f"{md.stem}.json", id=md.stem)
            for md in sorted(FIXTURES_DIR.glob("*.md"))
            if (FIXTURES_DIR / "expected_outputs" / f"{md.stem}.json").exists()
        ],
    )
    @pytest.mark.asyncio
    async def test_fixture_through_pipeline(self, md_file, expected_file):
        """
        Each fixture should pass through the full pipeline successfully.
        Mocks: scraper returns the fixture markdown, extractor returns expected output.
        """
        markdown = md_file.read_text()
        expected = json.loads(expected_file.read_text())
        extraction = {k: v for k, v in expected.items() if k != "_meta"}

        pipeline = _make_pipeline(
            scrape_return=markdown,
            extract_return=extraction,
        )

        result = await pipeline.ingest(f"https://fixture/{md_file.stem}")

        assert result is not None
        assert result.status == expected["status"]
        assert result.confidence == expected["confidence"]
        assert result.is_id_required == expected["is_id_required"]
