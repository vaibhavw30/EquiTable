# backend_ml/tests/agent/test_extraction_subgraph.py
"""Integration tests for the extraction subgraph.

Runs the compiled subgraph end-to-end against all 5 scraping fixtures using:
  - FakeScraper fed the fixture markdown
  - FakeStructuredModel returning the expected extraction
  - Real MongoDB round-trip via the test_db fixture
"""

import json
from pathlib import Path

from agent.cost import CostTracker
from agent.subgraph import build_extraction_subgraph
from agent.state import ExtractionResult
from tests.agent.conftest import FakeStructuredModel, FakeModelFactory, FakeScraper

FIX = Path(__file__).parent.parent / "fixtures" / "scraping"
NAMES = ["simple_static", "wordpress_complex", "minimal_info", "outdated_info", "multilingual"]


def _expected(name):
    data = json.loads((FIX / "expected_outputs" / f"{name}.json").read_text())
    data.pop("_meta", None)
    return data


async def test_subgraph_persists_each_fixture(test_db):
    """Invoke the subgraph for each of the 5 fixtures and verify MongoDB is updated."""
    for name in NAMES:
        await test_db["pantries"].insert_one({
            "name": name, "address": "a", "lat": 1.0, "lng": 2.0,
            "hours_notes": "OLD", "status": "UNKNOWN",
            "source_url": f"https://{name}.org",
            "last_updated": "2020-01-01T00:00:00Z",
        })
        expected = _expected(name)
        # Use expected.get(k) so missing optional fields default to None
        model = FakeStructuredModel(scripted=[ExtractionResult(**{
            k: expected.get(k) for k in ExtractionResult.model_fields
        })])
        factory = FakeModelFactory([model])
        markdown = (FIX / f"{name}.md").read_text()
        app = build_extraction_subgraph(
            FakeScraper(markdown=markdown), factory, CostTracker(1.0),
            lambda: "SYS", db=test_db,
        )
        final = await app.ainvoke({
            "source_url": f"https://{name}.org", "model_tier": 0,
            "retry_count": 0, "validation_errors": [],
        })
        assert final["outcome"] == "success", (
            f"Fixture '{name}': expected outcome='success', got '{final.get('outcome')}'"
        )
        doc = await test_db["pantries"].find_one({"source_url": f"https://{name}.org"})
        assert doc["confidence"] == expected["confidence"], (
            f"Fixture '{name}': expected confidence={expected['confidence']}, "
            f"got {doc['confidence']}"
        )
        assert doc["status"] == expected["status"], (
            f"Fixture '{name}': expected status={expected['status']!r}, "
            f"got {doc['status']!r}"
        )


async def test_subgraph_retries_then_succeeds(test_db):
    """Tier-0 returns invalid extraction (confidence=99); tier-1 returns valid.

    The subgraph should loop through bump_retry → extract with tier=1 and
    ultimately persist successfully.
    """
    await test_db["pantries"].insert_one({
        "name": "retry", "address": "a", "lat": 1.0, "lng": 2.0,
        "hours_notes": "OLD", "status": "UNKNOWN",
        "source_url": "https://retry.org", "last_updated": "2020-01-01T00:00:00Z",
    })
    bad = {"status": "OPEN", "hours_notes": "x", "hours_today": "x",
           "eligibility_rules": ["Open to all"], "is_id_required": False,
           "residency_req": None, "special_notes": None, "confidence": 99}  # invalid
    good = {**bad, "confidence": 8}
    # tier 0 returns invalid, tier 1 returns valid
    factory = FakeModelFactory([
        FakeStructuredModel(scripted=[bad]),
        FakeStructuredModel(scripted=[good]),
    ])
    app = build_extraction_subgraph(FakeScraper(), factory, CostTracker(1.0),
                                    lambda: "SYS", db=test_db)
    final = await app.ainvoke({"source_url": "https://retry.org", "model_tier": 0,
                               "retry_count": 0, "validation_errors": []})
    assert final["outcome"] == "success"
    assert 1 in factory.tiers_used        # escalated to tier 1
    doc = await test_db["pantries"].find_one({"source_url": "https://retry.org"})
    assert doc["confidence"] == 8
    assert doc["status"] == "OPEN"
