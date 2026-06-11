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


def _make_result(expected):
    """Build an ExtractionResult from an expected-output dict."""
    return ExtractionResult(**{k: expected.get(k) for k in ExtractionResult.model_fields})


async def test_subgraph_persists_each_fixture(test_db):
    """Invoke the subgraph for each of the 5 fixtures and verify MongoDB is updated.

    For the minimal_info fixture (confidence=2 < threshold 6) all 3 retry tiers
    are exhausted and the low-confidence result is still persisted.  We use a
    three-model FakeModelFactory to make tier escalation observable and assert
    it explicitly.
    """
    for name in NAMES:
        await test_db["pantries"].insert_one({
            "name": name, "address": "a", "lat": 1.0, "lng": 2.0,
            "hours_notes": "OLD", "status": "UNKNOWN",
            "source_url": f"https://{name}.org",
            "last_updated": "2020-01-01T00:00:00Z",
        })
        expected = _expected(name)
        result = _make_result(expected)

        if name == "minimal_info":
            # confidence=2 < threshold → subgraph exhausts all 3 tiers before persisting.
            # Supply three separate model instances (one per tier) so tiers_used is
            # [0, 1, 2] and each ainvoke call is independently tracked.
            factory = FakeModelFactory([
                FakeStructuredModel(scripted=[result]),
                FakeStructuredModel(scripted=[result]),
                FakeStructuredModel(scripted=[result]),
            ])
        else:
            # confidence >= threshold → single attempt on tier 0, success immediately.
            factory = FakeModelFactory([FakeStructuredModel(scripted=[result])])

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

        if name == "minimal_info":
            # All 3 tiers should have been used (0 → bump → 1 → bump → 2 → persist).
            assert final["retry_count"] == 2, (
                f"minimal_info: expected retry_count=2, got {final.get('retry_count')}"
            )
            assert factory.tiers_used == [0, 1, 2], (
                f"minimal_info: expected tiers_used=[0,1,2], got {factory.tiers_used}"
            )
        else:
            # High-confidence fixture: no retries, only tier 0 consulted.
            assert final["retry_count"] == 0, (
                f"Fixture '{name}': expected retry_count=0, got {final.get('retry_count')}"
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


async def test_subgraph_exhausts_retries_then_refuses_to_write(test_db):
    """All 3 model tiers return an invalid extraction (confidence=99).

    After exhausting MAX_RETRIES the subgraph persists with outcome="failed" and
    must NOT clobber the previously-known-good data already in the DB.
    """
    await test_db["pantries"].insert_one({
        "name": "exhaust", "address": "a", "lat": 1.0, "lng": 2.0,
        "hours_notes": "KNOWN GOOD", "status": "OPEN",
        "source_url": "https://exhaust.org",
        "confidence": 7,
        "last_updated": "2020-01-01T00:00:00Z",
    })
    # confidence=99 is out-of-range [1-10] → validate_extraction raises → validation_errors set
    bad = {"status": "OPEN", "hours_notes": "x", "hours_today": "x",
           "eligibility_rules": ["Open to all"], "is_id_required": False,
           "residency_req": None, "special_notes": None, "confidence": 99}
    factory = FakeModelFactory([
        FakeStructuredModel(scripted=[bad]),
        FakeStructuredModel(scripted=[bad]),
        FakeStructuredModel(scripted=[bad]),
    ])
    app = build_extraction_subgraph(
        FakeScraper(), factory, CostTracker(1.0), lambda: "SYS", db=test_db,
    )
    final = await app.ainvoke({
        "source_url": "https://exhaust.org", "model_tier": 0,
        "retry_count": 0, "validation_errors": [],
    })

    assert final["outcome"] == "failed", (
        f"Expected outcome='failed' after retry exhaustion, got '{final.get('outcome')}'"
    )

    # The DB doc must be UNCHANGED — bad extraction must NOT clobber good existing data.
    doc = await test_db["pantries"].find_one({"source_url": "https://exhaust.org"})
    assert doc["confidence"] == 7, (
        f"DB confidence was clobbered: expected 7, got {doc.get('confidence')}"
    )
    assert doc["status"] == "OPEN", (
        f"DB status was clobbered: expected 'OPEN', got {doc.get('status')!r}"
    )


async def test_subgraph_scrape_failure_skips_extraction(test_db):
    """A scrape returning None must short-circuit before any LLM call.

    The subgraph should exit immediately with outcome="failed", the model
    factory must never be consulted, and the existing DB doc must be unchanged.
    """
    await test_db["pantries"].insert_one({
        "name": "noscrape", "address": "a", "lat": 1.0, "lng": 2.0,
        "hours_notes": "KNOWN GOOD", "status": "OPEN",
        "source_url": "https://noscrape.org",
        "confidence": 5,
        "last_updated": "2020-01-01T00:00:00Z",
    })
    sentinel_model = FakeStructuredModel(scripted=[{
        "status": "OPEN", "hours_notes": "x", "hours_today": "x",
        "eligibility_rules": ["Open to all"], "is_id_required": False,
        "residency_req": None, "special_notes": None, "confidence": 8,
    }])
    factory = FakeModelFactory([sentinel_model])

    app = build_extraction_subgraph(
        FakeScraper(markdown=None), factory, CostTracker(1.0), lambda: "SYS", db=test_db,
    )
    final = await app.ainvoke({
        "source_url": "https://noscrape.org", "model_tier": 0,
        "retry_count": 0, "validation_errors": [],
    })

    assert final["outcome"] == "failed", (
        f"Expected outcome='failed' on scrape failure, got '{final.get('outcome')}'"
    )
    # No LLM call must have occurred — factory never consulted.
    assert factory.tiers_used == [], (
        f"Expected factory.tiers_used=[], got {factory.tiers_used}"
    )
    assert sentinel_model.calls == 0, (
        f"Expected 0 model calls, got {sentinel_model.calls}"
    )

    # DB doc is completely unchanged.
    doc = await test_db["pantries"].find_one({"source_url": "https://noscrape.org"})
    assert doc["confidence"] == 5, (
        f"DB confidence was modified: expected 5, got {doc.get('confidence')}"
    )
    assert doc["status"] == "OPEN", (
        f"DB status was modified: expected 'OPEN', got {doc.get('status')!r}"
    )
