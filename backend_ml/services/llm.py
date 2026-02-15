"""
LLM Service - Gemini client singleton and extraction facade.

The actual extraction logic lives in extractor.py. This module provides
backward-compatible access via get_llm_service() for existing code in main.py.
"""

import os
from typing import Optional

from google import genai
from dotenv import load_dotenv

from models.pantry import PantryUpdate
from services.extractor import ExtractorService

load_dotenv()


class LLMService:
    """
    Facade over ExtractorService for backward compatibility.
    Manages the Gemini client singleton and delegates extraction.
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in .env")

        self.client = genai.Client(api_key=api_key)
        self.extractor = ExtractorService(client=self.client)

    async def extract_data(self, raw_text: str) -> Optional[PantryUpdate]:
        """
        Extract structured PantryUpdate data from raw scraped text.
        Delegates to ExtractorService.
        """
        return await self.extractor.extract_to_pantry_update(raw_text)


# Singleton instance for reuse
_llm_instance: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Get or create a singleton LLMService instance."""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = LLMService()
    return _llm_instance
