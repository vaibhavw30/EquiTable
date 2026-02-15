"""
Ingestion Pipeline - Orchestrates the full scrape -> extract -> validate flow.

Single entry point for the ingest endpoint. Each stage logs structured events
so failures are traceable end-to-end.
"""

import logging
import time

from models.pantry import PantryUpdate, PantryStatus
from services.scraper import ScraperService
from services.extractor import ExtractorService, STATUS_MAP
from services.validator import validate_extraction, ValidationError

logger = logging.getLogger("equitable")


class IngestionError(Exception):
    """Raised when the ingestion pipeline fails at any stage."""

    def __init__(self, stage: str, reason: str, url: str):
        self.stage = stage
        self.reason = reason
        self.url = url
        super().__init__(f"Ingestion failed at '{stage}' for {url}: {reason}")


class IngestionPipeline:
    """
    Orchestrates: scrape -> extract -> validate.

    Each stage is independently testable; this class wires them together
    with structured logging and error handling.
    """

    def __init__(self, scraper: ScraperService, extractor: ExtractorService):
        self._scraper = scraper
        self._extractor = extractor

    async def ingest(self, url: str) -> PantryUpdate:
        """
        Run the full ingestion pipeline for a single URL.

        Args:
            url: The pantry website URL to scrape and extract.

        Returns:
            A validated PantryUpdate model.

        Raises:
            IngestionError: If any stage fails.
        """
        start = time.time()
        logger.info(
            "Ingestion started",
            extra={"event": "ingestion_start", "url": url},
        )

        # 1. Scrape
        markdown = await self._scrape(url)

        # 2. Extract
        data = await self._extract(url, markdown)

        # 3. Validate
        update = self._validate(url, data)

        duration_ms = round((time.time() - start) * 1000, 2)
        logger.info(
            "Ingestion complete",
            extra={
                "event": "ingestion_complete",
                "url": url,
                "confidence": update.confidence,
                "status": update.status,
                "duration_ms": duration_ms,
            },
        )

        return update

    async def _scrape(self, url: str) -> str:
        """Scrape the URL and return markdown content."""
        markdown = await self._scraper.scrape_url(url)
        if not markdown:
            raise IngestionError("scrape", "Scraper returned no content", url)
        return markdown

    async def _extract(self, url: str, markdown: str) -> dict:
        """Extract structured data from markdown."""
        data = await self._extractor.extract(markdown)
        if data is None:
            raise IngestionError("extract", "Extractor returned no data", url)
        return data

    def _validate(self, url: str, data: dict) -> PantryUpdate:
        """Validate extraction and convert to PantryUpdate."""
        try:
            validate_extraction(data)
        except ValidationError as e:
            raise IngestionError(
                "validate",
                f"Validation failed on '{e.field}': {e.reason}",
                url,
            )

        try:
            return PantryUpdate(
                status=STATUS_MAP.get(data.get("status", "UNKNOWN"), PantryStatus.UNKNOWN),
                hours_notes=data.get("hours_notes", "Not listed on website"),
                hours_today=data.get("hours_today", "Not listed"),
                eligibility_rules=data.get("eligibility_rules", ["Open to all - no restrictions listed"]),
                is_id_required=data.get("is_id_required", False),
                residency_req=data.get("residency_req"),
                special_notes=data.get("special_notes"),
                confidence=data.get("confidence", 1),
            )
        except Exception as e:
            raise IngestionError("validate", f"PantryUpdate construction: {e}", url)
