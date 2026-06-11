# backend_ml/tests/agent/test_load_sources.py
from datetime import datetime, timezone, timedelta
from agent.nodes.load_sources import make_load_sources_node


async def test_loads_only_stale_pantries_with_source_url(test_db):
    now = datetime.now(timezone.utc)
    await test_db["pantries"].insert_many([
        {"name": "stale", "address": "a", "lat": 1, "lng": 2, "hours_notes": "x",
         "source_url": "https://stale.org", "city": "Atlanta", "state": "GA",
         "last_updated": now - timedelta(hours=48)},
        {"name": "fresh", "address": "a", "lat": 1, "lng": 2, "hours_notes": "x",
         "source_url": "https://fresh.org",
         "last_updated": now - timedelta(hours=1)},
        {"name": "nourl", "address": "a", "lat": 1, "lng": 2, "hours_notes": "x",
         "last_updated": now - timedelta(hours=48)},
    ])
    node = make_load_sources_node(db=test_db)
    out = await node({})
    urls = {c["source_url"] for c in out["candidate_sources"]}
    assert urls == {"https://stale.org"}


async def test_joins_metrics(test_db):
    now = datetime.now(timezone.utc)
    await test_db["pantries"].insert_one(
        {"name": "p", "address": "a", "lat": 1, "lng": 2, "hours_notes": "x",
         "source_url": "https://p.org", "last_updated": now - timedelta(hours=48)})
    await test_db["source_metrics"].insert_one(
        {"source_url": "https://p.org", "consecutive_failures": 3, "success_rate": 0.5})
    node = make_load_sources_node(db=test_db)
    out = await node({})
    c = out["candidate_sources"][0]
    assert c["consecutive_failures"] == 3 and c["success_rate"] == 0.5
