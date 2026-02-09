"""
Test Intelligence Script - Verify Azure OpenAI Structured Output pipeline

Loads scraped_samples.json from Phase 2, feeds the first 2 items through
LLMService.extract_data(), and prints raw input vs. structured Pydantic
output for manual review.

Usage: python -m scripts.test_intelligence
"""

import asyncio
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.llm import LLMService

# Path to Phase 2 scraped samples
SCRAPED_SAMPLES_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scraped_samples.json"
)


async def test_extraction():
    """Test the LLM extraction pipeline using scraped samples."""
    print("=" * 70)
    print("EquiTable - Intelligence Pipeline Test (Phase 3)")
    print("=" * 70)

    # Load scraped samples
    if not os.path.exists(SCRAPED_SAMPLES_FILE):
        print(f"ERROR: {SCRAPED_SAMPLES_FILE} not found.")
        print("Run 'python -m scripts.test_ingestion' first to generate it.")
        sys.exit(1)

    with open(SCRAPED_SAMPLES_FILE, "r", encoding="utf-8") as f:
        samples = json.load(f)

    print(f"Loaded {len(samples)} scraped samples")

    # Only process the first 2 items
    samples_to_test = [s for s in samples[:2] if s.get("raw_content")]

    if not samples_to_test:
        print("ERROR: No samples with raw_content found.")
        sys.exit(1)

    print(f"Testing extraction on {len(samples_to_test)} samples...\n")

    # Initialize LLM service
    try:
        llm = LLMService()
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    for i, sample in enumerate(samples_to_test, 1):
        url = sample.get("url", "unknown")
        raw_content = sample["raw_content"]

        print(f"\n{'=' * 70}")
        print(f"[{i}/{len(samples_to_test)}] {url}")
        print(f"{'=' * 70}")

        # Show raw input (truncated)
        print(f"\n--- RAW INPUT ({len(raw_content)} chars) ---")
        preview = raw_content[:500]
        print(preview)
        if len(raw_content) > 500:
            print(f"  ... ({len(raw_content) - 500} more characters)")

        # Extract with LLM
        print(f"\n--- STRUCTURED OUTPUT ---")
        result = await llm.extract_data(raw_content)

        if result:
            print(f"  status:        {result.status}")
            print(f"  hours_today:   {result.hours_today}")
            print(f"  is_id_required: {result.is_id_required}")
            print(f"  residency_req: {result.residency_req}")
            print(f"  special_notes: {result.special_notes}")
            print(f"  confidence:    {result.confidence}/10")
            print(f"\n  Pydantic JSON: {result.model_dump_json(indent=2)}")
        else:
            print("  FAILED - No structured output returned")

    print(f"\n{'=' * 70}")
    print("Test complete.")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(test_extraction())
