# backend_ml/tests/agent/test_extract_node.py
from agent.cost import CostTracker
from agent.nodes.extract import make_extract_node
from tests.agent.conftest import FakeStructuredModel, FakeModelFactory

VALID = {
    "status": "OPEN", "hours_notes": "Mon 9-1", "hours_today": "9-1",
    "eligibility_rules": ["Open to all"], "is_id_required": False,
    "residency_req": None, "special_notes": None, "confidence": 8,
}


async def test_extract_populates_data_and_tracks_cost():
    model = FakeStructuredModel(scripted=[VALID])
    factory = FakeModelFactory([model])
    tracker = CostTracker(budget_usd=1.0)
    node = make_extract_node(factory, tracker, lambda: "SYSTEM PROMPT")
    out = await node({"raw_markdown": "# Pantry", "model_tier": 0,
                      "retry_count": 0, "validation_errors": []})
    assert out["extracted_data"]["status"] == "OPEN"
    assert out["confidence"] == 8
    assert tracker.spent_usd > 0          # usage recorded
    assert factory.tiers_used == [0]


async def test_extract_uses_escalated_tier_and_feeds_errors_back():
    model0 = FakeStructuredModel(scripted=[VALID])
    model1 = FakeStructuredModel(scripted=[VALID])
    factory = FakeModelFactory([model0, model1])
    tracker = CostTracker(budget_usd=1.0)
    node = make_extract_node(factory, tracker, lambda: "SYS")
    await node({"raw_markdown": "# Pantry", "model_tier": 1, "retry_count": 1,
                "validation_errors": ["confidence: must be 1-10, got 99"]})
    assert factory.tiers_used == [1]      # escalated tier used
    # the feedback string must reach the model's messages
    sent = model1  # second-tier model received the call
    assert sent.calls == 1


async def test_extract_handles_parse_error():
    """When with_structured_output returns parsed=None (parse failure),
    the node should return extracted_data=None without raising,
    and still record cost from raw.usage_metadata."""
    parse_exc = ValueError("unexpected token")
    model = FakeStructuredModel(scripted=[parse_exc])
    factory = FakeModelFactory([model])
    tracker = CostTracker(budget_usd=1.0)
    node = make_extract_node(factory, tracker, lambda: "SYS")
    out = await node({"raw_markdown": "# Pantry", "model_tier": 0,
                      "retry_count": 0, "validation_errors": []})
    assert out["extracted_data"] is None
    assert out["confidence"] is None
    assert tracker.spent_usd > 0          # cost still tracked from raw.usage_metadata
