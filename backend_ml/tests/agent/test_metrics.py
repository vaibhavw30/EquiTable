# backend_ml/tests/agent/test_metrics.py
from agent.nodes.metrics import make_update_metrics_node


async def test_success_increments_and_resets_consecutive(test_db):
    node = make_update_metrics_node(db=test_db)
    state = {"results": [
        {"source_url": "https://a.org", "outcome": "success", "latency_ms": 1200,
         "model_tier": 0, "had_validation_error": False},
    ]}
    await node(state)
    m = await test_db["source_metrics"].find_one({"source_url": "https://a.org"})
    assert m["successes"] == 1 and m["failures"] == 0
    assert m["consecutive_failures"] == 0
    assert m["success_rate"] == 1.0


async def test_failure_increments_consecutive(test_db):
    node = make_update_metrics_node(db=test_db)
    await node({"results": [{"source_url": "https://b.org", "outcome": "failed",
                             "latency_ms": 500, "model_tier": 2,
                             "had_validation_error": True}]})
    await node({"results": [{"source_url": "https://b.org", "outcome": "failed",
                             "latency_ms": 500, "model_tier": 2,
                             "had_validation_error": True}]})
    m = await test_db["source_metrics"].find_one({"source_url": "https://b.org"})
    assert m["failures"] == 2 and m["consecutive_failures"] == 2
    assert m["success_rate"] == 0.0
