# backend_ml/tests/agent/test_persist_node.py
from datetime import datetime, timezone
from agent.nodes.persist import make_persist_node

GOOD = {"status": "OPEN", "hours_notes": "Mon 9-1", "hours_today": "9-1",
        "eligibility_rules": ["Open to all"], "is_id_required": False,
        "residency_req": None, "special_notes": None, "confidence": 8}


async def test_persist_updates_dynamic_fields_only(test_db):
    await test_db["pantries"].insert_one({
        "name": "Existing Pantry", "address": "1 Main St", "lat": 1.0, "lng": 2.0,
        "location": {"type": "Point", "coordinates": [2.0, 1.0]},
        "hours_notes": "OLD", "status": "UNKNOWN", "confidence": 2,
        "source_url": "https://p.org", "city": "Atlanta", "state": "GA",
        "last_updated": datetime(2020, 1, 1, tzinfo=timezone.utc),
    })
    node = make_persist_node(db=test_db)
    out = await node({"source_url": "https://p.org", "extracted_data": GOOD,
                      "validation_errors": [], "confidence": 8})
    assert out["outcome"] == "success"
    doc = await test_db["pantries"].find_one({"source_url": "https://p.org"})
    assert doc["status"] == "OPEN"           # dynamic field updated
    assert doc["confidence"] == 8
    assert doc["name"] == "Existing Pantry"  # identity preserved


async def test_persist_records_scrape_method(test_db):
    GOOD_LOCAL = {"status": "OPEN", "hours_notes": "Mon 9-1", "hours_today": "9-1",
                  "eligibility_rules": ["Open to all"], "is_id_required": False,
                  "residency_req": None, "special_notes": None, "confidence": 8}
    await test_db["pantries"].insert_one({
        "name": "P", "address": "a", "lat": 1.0, "lng": 2.0, "hours_notes": "OLD",
        "status": "UNKNOWN", "confidence": 2, "source_url": "https://prov.org",
        "last_updated": datetime(2020, 1, 1, tzinfo=timezone.utc)})
    node = make_persist_node(db=test_db)
    await node({"source_url": "https://prov.org", "extracted_data": GOOD_LOCAL,
                "validation_errors": [], "confidence": 8, "scrape_method": "jina"})
    doc = await test_db["pantries"].find_one({"source_url": "https://prov.org"})
    assert doc["scrape_method"] == "jina"


async def test_persist_skips_write_when_still_invalid(test_db):
    await test_db["pantries"].insert_one({
        "name": "P", "address": "a", "lat": 1.0, "lng": 2.0,
        "hours_notes": "OLD", "status": "OPEN", "confidence": 7,
        "source_url": "https://q.org",
        "last_updated": datetime(2020, 1, 1, tzinfo=timezone.utc),
    })
    node = make_persist_node(db=test_db)
    out = await node({"source_url": "https://q.org", "extracted_data": GOOD,
                      "validation_errors": ["status: bad"], "confidence": 1})
    assert out["outcome"] == "failed"
    doc = await test_db["pantries"].find_one({"source_url": "https://q.org"})
    assert doc["confidence"] == 7            # untouched — good data not clobbered
