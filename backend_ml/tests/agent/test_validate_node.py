# backend_ml/tests/agent/test_validate_node.py
from agent.nodes.validate import validate_node

GOOD = {"status": "OPEN", "hours_notes": "x", "hours_today": "x",
        "eligibility_rules": ["Open to all"], "is_id_required": False, "confidence": 8}
BAD = {**GOOD, "confidence": 99}


async def test_validate_clears_errors_on_good_data():
    out = await validate_node({"extracted_data": GOOD})
    assert out["validation_errors"] == []


async def test_validate_records_error_on_bad_confidence():
    out = await validate_node({"extracted_data": BAD})
    assert len(out["validation_errors"]) == 1
    assert "confidence" in out["validation_errors"][0]


async def test_validate_handles_none_extracted_data():
    """When extract_node returns extracted_data=None (parse failure), validate
    should still return a validation_errors list so should_retry fires."""
    out = await validate_node({"extracted_data": None})
    assert len(out["validation_errors"]) > 0
    assert "confidence" in out["validation_errors"][0]
