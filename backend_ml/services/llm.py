"""
LLM Service - Uses Google Gemini to extract validated PantryUpdate data
from raw scraped Markdown.
"""

import os
import json
from datetime import datetime
from typing import Optional
from google import genai
from google.genai import types
from dotenv import load_dotenv

from models.pantry import PantryUpdate, PantryStatus

load_dotenv()

# Base system prompt - {current_date} will be injected at runtime
SYSTEM_PROMPT_TEMPLATE = """\
You are a data extraction agent for EquiTable, a food rescue app that helps \
people find food pantries in Atlanta.

TODAY IS: {current_date}

You will receive raw Markdown scraped from a food pantry or church website. \
Your job is to extract REAL, SPECIFIC information about their food \
assistance programs.

HOURS:
- Look for days and times (e.g. "Tuesday 1-6pm", "Mon-Fri 8:30am-4pm").
- For hours_notes, include the FULL weekly schedule, not just one day.
- For hours_today, use TODAY'S DATE ({current_date}) to determine the specific \
  hours. Look at the schedule and find the hours for {day_of_week}.
  - If the pantry is open today, return the hours (e.g., "10am-2pm").
  - If the pantry is closed today, return "Closed today".
  - If the schedule says "By Appointment", return "By appointment only".
  - If no schedule is listed, return "Hours not listed".
- Do NOT invent hours. Only extract what is explicitly stated.

ELIGIBILITY:
- Extract EVERY specific rule: residency requirements, ID requirements, \
  visit frequency limits, age priorities, family size limits, referral \
  requirements, appointment requirements.
- If the page mentions "by appointment only", include that as a rule AND \
  consider setting status to WAITLIST if availability seems limited.
- If the page says things like "open to all" or "no questions asked", \
  include that as a rule.
- If no rules are mentioned, return ["Open to all - no restrictions listed"].

ID REQUIREMENTS:
- Only mark is_id_required=true if the page EXPLICITLY mentions needing \
  ID, license, proof of address, or documentation.
- If the page does not mention ID at all, mark is_id_required=false \
  (assume no ID needed unless stated).

STATUS:
- OPEN if the pantry appears to be actively serving food on a regular schedule.
- CLOSED only if the page explicitly says closed, discontinued, or suspended.
- WAITLIST if they mention waiting lists, limited capacity, by-appointment-only \
  with limited slots, or if they require pre-registration.
- UNKNOWN only if the page has zero information about food programs \
  (e.g., a generic church homepage with no mention of food assistance).

CONFIDENCE:
- Rate 1-10 based on how much FOOD-PANTRY-SPECIFIC info is on the page.
- A generic church homepage with no pantry details = 2-3.
- A page mentioning a food program but with few details = 4-6.
- A dedicated food pantry page with hours and rules = 7-10.

Return a JSON object with these exact fields:
- status: one of "OPEN", "CLOSED", "WAITLIST", "UNKNOWN"
- hours_notes: string with full weekly schedule
- hours_today: string with today's ({day_of_week}) specific hours
- eligibility_rules: array of strings listing all requirements
- is_id_required: boolean
- residency_req: string or null
- special_notes: string or null
- confidence: integer 1-10\
"""

# JSON schema for structured output
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


def get_current_date_context() -> tuple[str, str]:
    """
    Get the current date formatted for the LLM prompt.
    Returns (full_date_string, day_of_week).
    Example: ("Saturday, February 8, 2026", "Saturday")
    """
    now = datetime.now()
    full_date = now.strftime("%A, %B %d, %Y")  # e.g., "Saturday, February 8, 2026"
    day_of_week = now.strftime("%A")  # e.g., "Saturday"
    return full_date, day_of_week


class LLMService:
    """
    Service for extracting structured PantryUpdate data from raw Markdown
    using Google Gemini.
    """

    def __init__(self):
        """
        Initialize the Gemini client.

        Loads GEMINI_API_KEY from environment.

        Raises:
            ValueError: If GEMINI_API_KEY is not set.
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env")

        self.client = genai.Client(api_key=api_key)

    def _build_system_prompt(self) -> str:
        """Build system prompt with current date injected."""
        current_date, day_of_week = get_current_date_context()
        return SYSTEM_PROMPT_TEMPLATE.format(
            current_date=current_date,
            day_of_week=day_of_week,
        )

    async def extract_data(self, raw_text: str) -> Optional[PantryUpdate]:
        """
        Extract structured PantryUpdate data from raw scraped text
        using Google Gemini.

        Args:
            raw_text: Raw Markdown content scraped from a pantry website.

        Returns:
            A validated PantryUpdate instance, or None on failure.
        """
        try:
            # Build prompt with current date
            system_prompt = self._build_system_prompt()

            response = self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=raw_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                ),
            )

            if not response.text:
                print("  Warning: Empty response from Gemini")
                return None

            # Parse the JSON response
            data = json.loads(response.text)

            # Map string status to enum
            status_map = {
                "OPEN": PantryStatus.OPEN,
                "CLOSED": PantryStatus.CLOSED,
                "WAITLIST": PantryStatus.WAITLIST,
                "UNKNOWN": PantryStatus.UNKNOWN,
            }

            result = PantryUpdate(
                status=status_map.get(data.get("status", "UNKNOWN"), PantryStatus.UNKNOWN),
                hours_notes=data.get("hours_notes", "Not listed on website"),
                hours_today=data.get("hours_today", "Not listed"),
                eligibility_rules=data.get("eligibility_rules", ["Open to all - no restrictions listed"]),
                is_id_required=data.get("is_id_required", False),
                residency_req=data.get("residency_req"),
                special_notes=data.get("special_notes"),
                confidence=data.get("confidence", 1),
            )

            print(f"  Extracted: status={result.status}, confidence={result.confidence}")
            return result

        except json.JSONDecodeError as e:
            print(f"  Error parsing JSON from Gemini: {e}")
            return None
        except Exception as e:
            print(f"  Error extracting data: {e}")
            return None


# Singleton instance for reuse
_llm_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create a singleton LLMService instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMService()
    return _llm_instance
