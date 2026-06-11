# backend_ml/tests/agent/test_retry_logic.py
from agent.nodes.validate import should_retry, bump_retry


def test_retry_on_validation_error():
    assert should_retry({"validation_errors": ["x"], "confidence": 9, "retry_count": 0}) == "retry"


def test_retry_on_low_confidence():
    assert should_retry({"validation_errors": [], "confidence": 4, "retry_count": 0}) == "retry"


def test_done_when_valid_and_confident():
    assert should_retry({"validation_errors": [], "confidence": 8, "retry_count": 0}) == "done"


def test_done_when_retries_exhausted():
    assert should_retry({"validation_errors": ["x"], "confidence": 2, "retry_count": 2}) == "done"


def test_retry_when_partway_through():
    assert should_retry({"validation_errors": ["x"], "confidence": 5, "retry_count": 1}) == "retry"


def test_bump_retry_increments_count_and_tier():
    out = bump_retry({"retry_count": 0, "model_tier": 0})
    assert out["retry_count"] == 1 and out["model_tier"] == 1
