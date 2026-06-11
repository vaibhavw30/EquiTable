"""Extract node — Gemini structured extraction with retry feedback + cost tracking.

Hardened against parse failures: when with_structured_output(include_raw=True)
returns {"parsed": None, "parsing_error": <exc>}, the node records cost from
raw.usage_metadata and returns extracted_data=None / confidence=None so the
downstream validate node sees empty data, fails, and triggers the retry edge.
"""

import logging
from langchain_core.messages import HumanMessage, SystemMessage
from agent.state import ExtractionState

logger = logging.getLogger("equitable")


def make_extract_node(model_factory, cost_tracker, system_prompt_builder):
    async def extract_node(state: ExtractionState) -> dict:
        tier = state.get("model_tier", 0)
        model = model_factory.get(tier)
        system = system_prompt_builder()

        feedback = ""
        prior_errors = state.get("validation_errors") or []
        if prior_errors:
            feedback = (
                "\n\nYOUR PREVIOUS ATTEMPT FAILED VALIDATION:\n"
                + "\n".join(f"- {e}" for e in prior_errors)
                + "\nFix these specific problems in your output."
            )

        messages = [
            SystemMessage(content=system),
            HumanMessage(content=(
                "Extract structured food pantry information from this scraped "
                f"webpage content:\n\n{state.get('raw_markdown', '')}{feedback}"
            )),
        ]

        result = await model.ainvoke(messages)
        parsed = result.get("parsed")
        raw = result.get("raw")

        # Always record cost from raw message, even on parse failure
        usage = getattr(raw, "usage_metadata", None) or {}
        cost_tracker.add_usage(
            model_factory.name_for_tier(tier),
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )

        # Handle parse failure: parsed is None or parsing_error is set
        if result.get("parsing_error") is not None or parsed is None:
            logger.warning(
                "Agent extraction parse error",
                extra={
                    "event": "agent_extract_parse_error",
                    "source_url": state.get("source_url"),
                    "tier": tier,
                },
            )
            return {"extracted_data": None, "confidence": None}

        data = parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)
        return {"extracted_data": data, "confidence": data.get("confidence")}
    return extract_node
