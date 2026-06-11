"""Per-run token→USD cost accounting and budget enforcement."""

from agent.config import MODEL_PRICING


class CostTracker:
    """Per-run token→USD accounting + budget checks.

    No lock needed: the refresh pipeline runs on a single asyncio event loop
    (fan-out is asyncio.gather, not threads), so increments to _spent are not
    subject to data races.
    """

    def __init__(self, budget_usd: float):
        self.budget_usd = budget_usd
        self._spent = 0.0

    def add_usage(self, model: str, input_tokens: int, output_tokens: int) -> None:
        in_price, out_price = MODEL_PRICING.get(model, (0.0, 0.0))
        cost = (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
        self._spent += cost

    @property
    def spent_usd(self) -> float:
        return self._spent

    @property
    def remaining_usd(self) -> float:
        return self.budget_usd - self._spent

    @property
    def is_exhausted(self) -> bool:
        return self._spent >= self.budget_usd
