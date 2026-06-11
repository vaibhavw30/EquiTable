from agent.cost import CostTracker


def test_add_usage_accumulates_cost():
    t = CostTracker(budget_usd=1.0)
    # 1,000,000 input + 1,000,000 output on flash-lite = 0.075 + 0.30 = 0.375
    t.add_usage("gemini-2.0-flash-lite", input_tokens=1_000_000, output_tokens=1_000_000)
    assert round(t.spent_usd, 4) == 0.375


def test_remaining_and_exhausted():
    t = CostTracker(budget_usd=0.40)
    t.add_usage("gemini-2.0-flash-lite", 1_000_000, 1_000_000)  # 0.375
    assert round(t.remaining_usd, 4) == 0.025
    assert t.is_exhausted is False
    t.add_usage("gemini-2.0-flash-lite", 0, 1_000_000)          # +0.30 → 0.675
    assert t.is_exhausted is True


def test_unknown_model_costs_zero_but_does_not_crash():
    t = CostTracker(budget_usd=1.0)
    t.add_usage("made-up-model", 1000, 1000)
    assert t.spent_usd == 0.0
