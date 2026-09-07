from agent.cost import CostTracker


def test_add_usage_accumulates_cost():
    t = CostTracker(budget_usd=2.0)
    # 1,000,000 input + 1,000,000 output on flash-lite = 0.25 + 1.50 = 1.75
    t.add_usage("gemini-3.1-flash-lite", input_tokens=1_000_000, output_tokens=1_000_000)
    assert round(t.spent_usd, 4) == 1.75


def test_remaining_and_exhausted():
    t = CostTracker(budget_usd=2.0)
    t.add_usage("gemini-3.1-flash-lite", 1_000_000, 1_000_000)  # 1.75
    assert round(t.remaining_usd, 4) == 0.25
    assert t.is_exhausted is False
    t.add_usage("gemini-3.1-flash-lite", 0, 1_000_000)          # +1.50 → 3.25
    assert t.is_exhausted is True


def test_pricing_matches_current_gemini3_rates():
    """Lock in the current official per-1M-token rates (thinking tokens bill as
    output). flash-lite 0.25/1.50, 3.5-flash 1.50/9.00, pro-preview 2.00/12.00."""
    lite = CostTracker(budget_usd=100.0)
    lite.add_usage("gemini-3.1-flash-lite", 1_000_000, 1_000_000)
    assert round(lite.spent_usd, 4) == 1.75            # 0.25 + 1.50

    flash = CostTracker(budget_usd=100.0)
    flash.add_usage("gemini-3.5-flash", 1_000_000, 1_000_000)
    assert round(flash.spent_usd, 4) == 10.50          # 1.50 + 9.00

    pro = CostTracker(budget_usd=100.0)
    pro.add_usage("gemini-3.1-pro-preview", 1_000_000, 1_000_000)
    assert round(pro.spent_usd, 4) == 14.00            # 2.00 + 12.00


def test_unknown_model_costs_zero_but_does_not_crash():
    t = CostTracker(budget_usd=1.0)
    t.add_usage("made-up-model", 1000, 1000)
    assert t.spent_usd == 0.0
