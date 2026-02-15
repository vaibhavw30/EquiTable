"""
Extractor Service - Uses Google Gemini to extract structured pantry data
from scraped Markdown.

Loads the system prompt and few-shot examples from version-controlled
files in backend_ml/prompts/.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types

from models.pantry import PantryUpdate, PantryStatus

logger = logging.getLogger("equitable")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# JSON schema for Gemini structured output
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {
            "type": "string",
            "enum": ["OPEN", "CLOSED", "WAITLIST", "UNKNOWN"],
        },
        "hours_notes": {"type": "string"},
        "hours_today": {"type": "string"},
        "eligibility_rules": {
            "type": "array",
            "items": {"type": "string"},
        },
        "is_id_required": {"type": "boolean"},
        "residency_req": {"type": "string"},
        "special_notes": {"type": "string"},
        "confidence": {"type": "integer"},
    },
    "required": [
        "status",
        "hours_notes",
        "hours_today",
        "eligibility_rules",
        "is_id_required",
        "confidence",
    ],
}

STATUS_MAP = {
    "OPEN": PantryStatus.OPEN,
    "CLOSED": PantryStatus.CLOSED,
    "WAITLIST": PantryStatus.WAITLIST,
    "UNKNOWN": PantryStatus.UNKNOWN,
}


def get_current_date_context() -> tuple[str, str]:
    """
    Get the current date formatted for the LLM prompt.
    Returns (full_date_string, day_of_week).
    """
    now = datetime.now()
    full_date = now.strftime("%A, %B %d, %Y")
    day_of_week = now.strftime("%A")
    return full_date, day_of_week


def _load_prompt_file(filename: str) -> str:
    """Load a prompt file from the prompts directory."""
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text()


class ExtractorService:
    """
    Service for extracting structured PantryUpdate data from Markdown
    using Google Gemini with versioned prompts and few-shot examples.
    """

    def __init__(self, client: genai.Client):
        self._client = client
        self._system_prompt_template = _load_prompt_file("extraction_system.md")
        self._examples = _load_prompt_file("extraction_examples.md")

    def _build_system_prompt(self) -> str:
        """Build system prompt with current date injected + few-shot examples."""
        current_date, day_of_week = get_current_date_context()
        prompt = self._system_prompt_template.format(
            current_date=current_date,
            day_of_week=day_of_week,
        )
        prompt += "\n\n---\n\n" + self._examples
        return prompt

    async def extract(self, markdown: str) -> Optional[dict]:
        """
        Extract structured pantry data from Markdown.

        Args:
            markdown: Raw Markdown content from a scraped pantry page.

        Returns:
            A raw extraction dict, or None on failure.
        """
        start = time.time()

        try:
            system_prompt = self._build_system_prompt()

            user_message = f"Extract structured food pantry information from this scraped webpage content:\n\n{markdown}"

            response = self._client.models.generate_content(
                model="gemini-2.0-flash",
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                    temperature=0,
                ),
            )

            duration_ms = round((time.time() - start) * 1000, 2)

            if not response.text:
                logger.error(
                    "Extraction failed",
                    extra={"event": "extraction_failed", "error": "Empty response from Gemini", "duration_ms": duration_ms},
                )
                return None

            data = json.loads(response.text)

            confidence = data.get("confidence", 0)
            logger.info(
                "Extraction complete",
                extra={
                    "event": "extraction_complete",
                    "confidence": confidence,
                    "status": data.get("status"),
                    "duration_ms": duration_ms,
                },
            )

            if confidence <= 4:
                logger.warning(
                    "Low confidence extraction",
                    extra={
                        "event": "low_confidence",
                        "confidence": confidence,
                        "status": data.get("status"),
                    },
                )

            return data

        except json.JSONDecodeError as e:
            duration_ms = round((time.time() - start) * 1000, 2)
            logger.error(
                "Extraction failed",
                extra={"event": "extraction_failed", "error": f"JSON parse error: {e}", "duration_ms": duration_ms},
            )
            return None
        except Exception as e:
            duration_ms = round((time.time() - start) * 1000, 2)
            logger.error(
                "Extraction failed",
                extra={"event": "extraction_failed", "error": str(e), "duration_ms": duration_ms},
            )
            return None

    async def extract_to_pantry_update(self, markdown: str) -> Optional[PantryUpdate]:
        """
        Extract and convert to a validated PantryUpdate model.

        Convenience method that wraps extract() + PantryUpdate construction.
        """
        data = await self.extract(markdown)
        if data is None:
            return None

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
            logger.error(
                "Extraction failed",
                extra={"event": "extraction_failed", "error": f"PantryUpdate construction: {e}"},
            )
            return None
