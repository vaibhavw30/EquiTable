"""Tiered Gemini model factory with structured output.

The default builder wraps ChatGoogleGenerativeAI with structured output
(include_raw=True) so callers get both the parsed ExtractionResult and the
raw AIMessage (for usage_metadata / cost tracking). A builder can be injected
for tests so no network call is made.
"""

import os
from typing import Callable, Optional

from agent.config import model_for_tier
from agent.state import ExtractionResult


def _default_builder(model_name: str):
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )
    return llm.with_structured_output(ExtractionResult, include_raw=True)


class ModelFactory:
    def __init__(self, builder: Optional[Callable[[str], object]] = None):
        self._builder = builder or _default_builder
        self._cache: dict[str, object] = {}

    def get(self, tier: int):
        name = model_for_tier(tier)
        if name not in self._cache:
            self._cache[name] = self._builder(name)
        return self._cache[name]
