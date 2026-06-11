# Food Rescue Agent — LangGraph Refresh Pipeline Implementation Plan (Plan 1 of 2: the agent)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone, scheduled-ready background refresh job — a LangGraph multi-agent state machine that re-scrapes stale pantries with a curator agent, a conditional retry/escalation loop, a MongoDB checkpointer, per-run cost budgeting, and LangSmith tracing — runnable as `python -m agent.refresh`.

**Architecture:** A parent LangGraph (`load_sources → curator → process_sources → aggregate_report → update_metrics`) fans out (under an asyncio semaphore, gated by a cost budget) to a reusable **extraction subgraph** (`scrape → extract → validate → [retry|persist]`). The subgraph's retry edge feeds validation/low-confidence signals back into the extractor and escalates the Gemini model tier. Existing services (`ScraperService`, `validate_extraction`, prompt files, `Pantry` model) are reused, not duplicated.

**Tech Stack:** Python 3.10+, LangGraph, langchain-google-genai (Gemini 2.0 Flash-Lite → 2.0 Flash → 2.5 Flash), langgraph-checkpoint-mongodb, langsmith, Motor (MongoDB Atlas), pytest + pytest-asyncio.

**Scope note:** This plan covers the agent code only. AWS deployment (Dockerfile → ECR → Fargate → EventBridge) is **Plan 2**, written separately. ADR-019 (Fargate/no-NAT) lands in Plan 2; ADRs 015–018 and 020 land here (Task 18).

**Spec:** `docs/superpowers/specs/2026-06-11-food-rescue-agent-rebuild-design.md`

**Conventions used throughout:**
- All commands run from `backend_ml/` with the venv active: `cd backend_ml && source venv/bin/activate`.
- `pytest.ini` sets `asyncio_mode = auto`, so async test functions need no `@pytest.mark.asyncio`.
- DB-touching tests use the existing `test_db` fixture from `tests/conftest.py` (Atlas `equitable_test`, dropped per test).
- New agent tests live in `backend_ml/tests/agent/`.
- Commit after every task. Branch: continue on `docs/food-rescue-agent-rebuild-spec` or create `feature/langgraph-refresh-agent` (recommended) before Task 1.

---

## File Structure

**Created (agent package):**
- `backend_ml/agent/__init__.py` — package marker
- `backend_ml/agent/config.py` — tunable constants, model ladder, pricing, LangSmith setup
- `backend_ml/agent/state.py` — `ExtractionResult` (Pydantic), `ExtractionState`, `ParentState` (TypedDicts)
- `backend_ml/agent/cost.py` — `CostTracker` (token→USD accounting + budget checks)
- `backend_ml/agent/models.py` — `ModelFactory` (tiered `ChatGoogleGenerativeAI` with structured output)
- `backend_ml/agent/prompts.py` — thin reuse layer over `services/extractor` prompt loading
- `backend_ml/agent/nodes/__init__.py`
- `backend_ml/agent/nodes/scrape.py` — wraps `ScraperService`
- `backend_ml/agent/nodes/extract.py` — Gemini extraction + retry feedback
- `backend_ml/agent/nodes/validate.py` — wraps `validate_extraction`
- `backend_ml/agent/nodes/persist.py` — upsert dynamic fields onto existing pantry
- `backend_ml/agent/nodes/curator.py` — rank/select stale sources
- `backend_ml/agent/nodes/load_sources.py` — query stale pantries + join metrics
- `backend_ml/agent/nodes/aggregate.py` — run summary
- `backend_ml/agent/nodes/metrics.py` — write `source_metrics`
- `backend_ml/agent/subgraph.py` — assemble + compile extraction subgraph
- `backend_ml/agent/graph.py` — assemble + compile parent graph (incl. process_sources fan-out)
- `backend_ml/agent/checkpointer.py` — MongoDB checkpointer context manager
- `backend_ml/agent/cli.py` — `python -m agent.refresh` entrypoint

**Created (tests):**
- `backend_ml/tests/agent/__init__.py`
- `backend_ml/tests/agent/conftest.py` — fakes (FakeModel, FakeScraper) + helpers
- `backend_ml/tests/agent/test_cost.py`
- `backend_ml/tests/agent/test_models.py`
- `backend_ml/tests/agent/test_extract_node.py`
- `backend_ml/tests/agent/test_validate_node.py`
- `backend_ml/tests/agent/test_retry_logic.py`
- `backend_ml/tests/agent/test_persist_node.py`
- `backend_ml/tests/agent/test_extraction_subgraph.py` — against the 5 fixtures
- `backend_ml/tests/agent/test_metrics.py`
- `backend_ml/tests/agent/test_load_sources.py`
- `backend_ml/tests/agent/test_curator.py`
- `backend_ml/tests/agent/test_graph.py` — parent graph + budget gate
- `backend_ml/tests/agent/test_checkpointer.py` — resume
- `backend_ml/tests/agent/test_smoke_refresh.py` — end-to-end

**Modified:**
- `backend_ml/requirements.txt` — add langgraph stack, remove braintrust
- `backend_ml/main.py:11-15` — remove Braintrust block
- `docs/decisions.md` — append ADR-015..018, 020

---

## Phase 0 — Scaffolding & dependencies

### Task 1: Dependencies, package skeleton, remove Braintrust

**Files:**
- Modify: `backend_ml/requirements.txt`
- Modify: `backend_ml/main.py:5-15`
- Create: `backend_ml/agent/__init__.py`
- Create: `backend_ml/tests/agent/__init__.py`

- [ ] **Step 1: Replace the Braintrust block in `main.py`.** Replace lines 5–15 (the `import os` + Braintrust guard) with just:

```python
import os
```

(Remove the entire `if os.getenv("BRAINTRUST_API_KEY"): ...` block. LangSmith tracing is wired in the agent package, not the API.)

- [ ] **Step 2: Update `requirements.txt`.** Remove the line `braintrust>=0.23.0`. Add under a new heading:

```
# Agent (LangGraph refresh pipeline)
langgraph>=0.2.50
langchain-core>=0.3.0
langchain-google-genai>=2.0.0
langgraph-checkpoint-mongodb>=0.1.0
langsmith>=0.1.0
```

- [ ] **Step 3: Install.**

Run: `cd backend_ml && source venv/bin/activate && pip install -r requirements.txt`
Expected: installs langgraph, langchain-google-genai, langgraph-checkpoint-mongodb, langsmith without error.

- [ ] **Step 4: Create empty package markers.**

```python
# backend_ml/agent/__init__.py
"""EquiTable Food Rescue Agent — LangGraph refresh pipeline."""
```
```python
# backend_ml/tests/agent/__init__.py
```

- [ ] **Step 5: Verify the API still imports (no Braintrust).**

Run: `cd backend_ml && python -c "import main; print('ok')"`
Expected: prints `ok` with no Braintrust ImportError.

- [ ] **Step 6: Verify existing tests still pass (regression guard).**

Run: `cd backend_ml && python -m pytest tests/test_smoke.py -v`
Expected: all smoke tests PASS.

- [ ] **Step 7: Commit.**

```bash
git add backend_ml/requirements.txt backend_ml/main.py backend_ml/agent/__init__.py backend_ml/tests/agent/__init__.py
git commit -m "chore: scaffold agent package, swap Braintrust deps for LangGraph stack"
```

---

### Task 2: Config — constants, model ladder, pricing, LangSmith setup

**Files:**
- Create: `backend_ml/agent/config.py`

- [ ] **Step 1: Write `config.py`.**

```python
"""Tunable configuration for the refresh agent.

All knobs live here so behavior is adjustable without touching graph logic.
Pricing values are USD per 1,000,000 tokens — VERIFY against current Gemini
pricing before relying on cost numbers; they drift over time.
"""

import os

# ── Refresh-run knobs ─────────────────────────────────────────────────────
FRESHNESS_FLOOR_HOURS = 24      # only pantries staler than this are candidates
MAX_SOURCES_PER_RUN = 25        # curator selects at most this many per run
MAX_CONCURRENT = 4              # concurrent extraction subgraphs
CONFIDENCE_THRESHOLD = 6        # confidence below this triggers a retry
MAX_RETRIES = 2                 # retries after the initial attempt (3 attempts total)
QUARANTINE_THRESHOLD = 5        # consecutive_failures above this → skip + report
MAX_COST_USD = 0.50             # per-run dollar budget

# ── Model ladder (cheap-first with escalation) ────────────────────────────
# Index 0 = initial attempt, escalating per retry. The last rung is reused
# if retries exceed the ladder length.
EXTRACTION_MODEL_LADDER = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]
CURATOR_MODEL = "gemini-2.0-flash-lite"

# ── Pricing: model -> (input_per_1M, output_per_1M) in USD ────────────────
MODEL_PRICING = {
    "gemini-2.0-flash-lite": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
}


def model_for_tier(tier: int) -> str:
    """Return the model name for an escalation tier (clamped to the ladder)."""
    idx = min(tier, len(EXTRACTION_MODEL_LADDER) - 1)
    return EXTRACTION_MODEL_LADDER[idx]


def setup_langsmith() -> None:
    """Enable LangSmith tracing if an API key is present (no-op otherwise)."""
    if os.getenv("LANGCHAIN_API_KEY") or os.getenv("LANGSMITH_API_KEY"):
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", "equitable-refresh-agent")
```

- [ ] **Step 2: Verify it imports and the ladder clamps.**

Run: `cd backend_ml && python -c "from agent.config import model_for_tier; print(model_for_tier(0), model_for_tier(5))"`
Expected: `gemini-2.0-flash-lite gemini-2.5-flash`

- [ ] **Step 3: Commit.**

```bash
git add backend_ml/agent/config.py
git commit -m "feat(agent): add config — constants, model ladder, pricing, langsmith setup"
```

---

### Task 3: State definitions

**Files:**
- Create: `backend_ml/agent/state.py`

- [ ] **Step 1: Write `state.py`.** `ExtractionResult` mirrors the existing `RESPONSE_SCHEMA` in `services/extractor.py` so structured output is type-safe.

```python
"""Typed state for the refresh agent graphs."""

from typing import Optional, TypedDict
from pydantic import BaseModel, Field


class ExtractionResult(BaseModel):
    """Structured-output schema for Gemini extraction (mirrors RESPONSE_SCHEMA)."""
    status: str = Field(description="OPEN | CLOSED | WAITLIST | UNKNOWN")
    hours_notes: str
    hours_today: str
    eligibility_rules: list[str]
    is_id_required: bool
    residency_req: Optional[str] = None
    special_notes: Optional[str] = None
    confidence: int = Field(description="1-10")


class ExtractionState(TypedDict, total=False):
    """State threaded through the per-source extraction subgraph."""
    source_url: str
    pantry_id: str
    raw_markdown: Optional[str]
    extracted_data: Optional[dict]
    validation_errors: list[str]
    confidence: Optional[int]
    retry_count: int
    model_tier: int
    latency_ms: float
    outcome: str            # "success" | "failed" | "skipped_budget"
    final_update: Optional[dict]


class ParentState(TypedDict, total=False):
    """State for the top-level refresh graph."""
    run_id: str
    candidate_sources: list[dict]
    selected_sources: list[dict]      # subset of candidates the curator chose
    curator_reasoning: str
    quarantined: list[dict]
    results: list[dict]               # one summary dict per processed source
    cost_spent_usd: float
    cost_budget_usd: float
```

- [ ] **Step 2: Verify import + schema.**

Run: `cd backend_ml && python -c "from agent.state import ExtractionResult; print(ExtractionResult.model_json_schema()['required'])"`
Expected: a list including `status`, `hours_notes`, `hours_today`, `eligibility_rules`, `is_id_required`, `confidence`.

- [ ] **Step 3: Commit.**

```bash
git add backend_ml/agent/state.py
git commit -m "feat(agent): add typed state (ExtractionResult, ExtractionState, ParentState)"
```

---

## Phase 1 — Extraction subgraph

### Task 4: Cost tracker

**Files:**
- Create: `backend_ml/agent/cost.py`
- Test: `backend_ml/tests/agent/test_cost.py`

- [ ] **Step 1: Write the failing test.**

```python
# backend_ml/tests/agent/test_cost.py
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
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_cost.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.cost'`.

- [ ] **Step 3: Write `cost.py`.**

```python
"""Per-run token→USD cost accounting and budget enforcement."""

import threading
from agent.config import MODEL_PRICING


class CostTracker:
    def __init__(self, budget_usd: float):
        self.budget_usd = budget_usd
        self._spent = 0.0
        self._lock = threading.Lock()

    def add_usage(self, model: str, input_tokens: int, output_tokens: int) -> None:
        in_price, out_price = MODEL_PRICING.get(model, (0.0, 0.0))
        cost = (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
        with self._lock:
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
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_cost.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/cost.py backend_ml/tests/agent/test_cost.py
git commit -m "feat(agent): add CostTracker with budget enforcement"
```

---

### Task 5: Prompt reuse layer

**Files:**
- Create: `backend_ml/agent/prompts.py`

- [ ] **Step 1: Write `prompts.py`** (reuses the existing prompt files + date logic from `services/extractor.py`, DRY — no prompt duplication).

```python
"""Builds the extraction system prompt by reusing services/extractor loaders."""

from services.extractor import _load_prompt_file, get_current_date_context


def build_extraction_system_prompt() -> str:
    """Same composition the live extractor uses: dated system prompt + examples."""
    template = _load_prompt_file("extraction_system.md")
    examples = _load_prompt_file("extraction_examples.md")
    current_date, day_of_week = get_current_date_context()
    prompt = template.format(current_date=current_date, day_of_week=day_of_week)
    return prompt + "\n\n---\n\n" + examples
```

- [ ] **Step 2: Verify it builds a non-empty prompt.**

Run: `cd backend_ml && python -c "from agent.prompts import build_extraction_system_prompt as b; print(len(b()) > 100)"`
Expected: `True`

- [ ] **Step 3: Commit.**

```bash
git add backend_ml/agent/prompts.py
git commit -m "feat(agent): add prompt reuse layer over services/extractor"
```

---

### Task 6: Model factory

**Files:**
- Create: `backend_ml/agent/models.py`
- Test: `backend_ml/tests/agent/test_models.py`

- [ ] **Step 1: Write the failing test.** We test the tier→model-name mapping (deterministic, no network). The factory accepts an injectable builder so tests never hit the API.

```python
# backend_ml/tests/agent/test_models.py
from agent.models import ModelFactory


def test_factory_uses_correct_model_per_tier():
    seen = []

    def fake_builder(model_name):
        seen.append(model_name)
        return f"client::{model_name}"

    f = ModelFactory(builder=fake_builder)
    assert f.get(0) == "client::gemini-2.0-flash-lite"
    assert f.get(1) == "client::gemini-2.0-flash"
    assert f.get(2) == "client::gemini-2.5-flash"
    assert f.get(9) == "client::gemini-2.5-flash"   # clamps to last rung


def test_factory_caches_per_tier():
    calls = []

    def fake_builder(model_name):
        calls.append(model_name)
        return object()

    f = ModelFactory(builder=fake_builder)
    a = f.get(0)
    b = f.get(0)
    assert a is b               # cached, builder called once
    assert calls == ["gemini-2.0-flash-lite"]
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agent.models'`.

- [ ] **Step 3: Write `models.py`.**

```python
"""Tiered Gemini model factory with structured output.

The default builder wraps ChatGoogleGenerativeAI with structured output
(include_raw=True) so callers get both the parsed ExtractionResult and the
raw AIMessage (for usage_metadata / cost tracking). A builder can be injected
for tests so no network call is made.
"""

import os
from typing import Callable, Optional

from agent.config import model_for_tier
from agent.state import ExtractionResult


def _default_builder(model_name: str):
    from langchain_google_genai import ChatGoogleGenerativeAI
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )
    return llm.with_structured_output(ExtractionResult, include_raw=True)


class ModelFactory:
    def __init__(self, builder: Optional[Callable[[str], object]] = None):
        self._builder = builder or _default_builder
        self._cache: dict[str, object] = {}

    def get(self, tier: int):
        name = model_for_tier(tier)
        if name not in self._cache:
            self._cache[name] = self._builder(name)
        return self._cache[name]
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_models.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/models.py backend_ml/tests/agent/test_models.py
git commit -m "feat(agent): add tiered ModelFactory with injectable builder"
```

---

### Task 7: Shared test fakes

**Files:**
- Create: `backend_ml/tests/agent/conftest.py`

- [ ] **Step 1: Write the fakes** used by node/subgraph tests (no network, deterministic).

```python
# backend_ml/tests/agent/conftest.py
"""Fakes for agent node/subgraph tests — no network, deterministic."""

from agent.state import ExtractionResult


class FakeRawMessage:
    """Stands in for a LangChain AIMessage carrying usage_metadata."""
    def __init__(self, input_tokens=100, output_tokens=50):
        self.usage_metadata = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        }


class FakeStructuredModel:
    """Mimics ChatGoogleGenerativeAI.with_structured_output(..., include_raw=True).

    `scripted` is a list of ExtractionResult (or dict) returned in order per
    ainvoke call, letting a test simulate 'fail then succeed' retries.
    """
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = 0

    async def ainvoke(self, messages):
        result = self._scripted[min(self.calls, len(self._scripted) - 1)]
        self.calls += 1
        if isinstance(result, dict):
            result = ExtractionResult(**result)
        return {"raw": FakeRawMessage(), "parsed": result, "parsing_error": None}


class FakeModelFactory:
    """Returns a FakeStructuredModel per tier; records which tiers were used."""
    def __init__(self, scripted_by_tier):
        self._by_tier = scripted_by_tier
        self.tiers_used = []

    def get(self, tier):
        self.tiers_used.append(tier)
        idx = min(tier, len(self._by_tier) - 1)
        return self._by_tier[idx]


class FakeScraper:
    """Mimics ScraperService.scrape_url."""
    def __init__(self, markdown="# Pantry\nMon-Fri 9am-5pm. No ID required."):
        self._markdown = markdown

    async def scrape_url(self, url):
        return self._markdown
```

- [ ] **Step 2: Verify importable.**

Run: `cd backend_ml && python -c "import tests.agent.conftest" 2>/dev/null; echo done`
Expected: prints `done` (no traceback). (pytest will import it automatically as a conftest.)

- [ ] **Step 3: Commit.**

```bash
git add backend_ml/tests/agent/conftest.py
git commit -m "test(agent): add shared fakes (FakeModel, FakeScraper, FakeModelFactory)"
```

---

### Task 8: Scrape node

**Files:**
- Create: `backend_ml/agent/nodes/__init__.py`
- Create: `backend_ml/agent/nodes/scrape.py`
- Test: `backend_ml/tests/agent/test_scrape_node.py`

- [ ] **Step 1: Write the failing test.**

```python
# backend_ml/tests/agent/test_scrape_node.py
import time
from agent.nodes.scrape import make_scrape_node
from tests.agent.conftest import FakeScraper


async def test_scrape_node_populates_markdown_and_latency():
    node = make_scrape_node(FakeScraper(markdown="# Food Pantry\nOpen Mondays"))
    out = await node({"source_url": "https://x.org", "model_tier": 0, "retry_count": 0})
    assert "Food Pantry" in out["raw_markdown"]
    assert out["latency_ms"] >= 0


async def test_scrape_node_empty_marks_failed():
    node = make_scrape_node(FakeScraper(markdown=None))
    out = await node({"source_url": "https://x.org"})
    assert out["raw_markdown"] is None
    assert out["outcome"] == "failed"
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_scrape_node.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write the nodes package + scrape node.**

```python
# backend_ml/agent/nodes/__init__.py
```
```python
# backend_ml/agent/nodes/scrape.py
"""Scrape node — wraps ScraperService (services/scraper.py)."""

import time
from agent.state import ExtractionState


def make_scrape_node(scraper):
    async def scrape_node(state: ExtractionState) -> dict:
        start = time.time()
        markdown = await scraper.scrape_url(state["source_url"])
        latency_ms = round((time.time() - start) * 1000, 2)
        if not markdown:
            return {"raw_markdown": None, "latency_ms": latency_ms, "outcome": "failed"}
        return {"raw_markdown": markdown, "latency_ms": latency_ms}
    return scrape_node
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_scrape_node.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/nodes/__init__.py backend_ml/agent/nodes/scrape.py backend_ml/tests/agent/test_scrape_node.py
git commit -m "feat(agent): add scrape node wrapping ScraperService"
```

---

### Task 9: Extract node (with retry feedback + cost tracking)

**Files:**
- Create: `backend_ml/agent/nodes/extract.py`
- Test: `backend_ml/tests/agent/test_extract_node.py`

- [ ] **Step 1: Write the failing test.**

```python
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
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_extract_node.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `extract.py`.**

```python
# backend_ml/agent/nodes/extract.py
"""Extract node — Gemini structured extraction with retry feedback + cost tracking."""

from langchain_core.messages import HumanMessage, SystemMessage
from agent.config import model_for_tier
from agent.state import ExtractionState


def make_extract_node(model_factory, cost_tracker, system_prompt_builder):
    async def extract_node(state: ExtractionState) -> dict:
        tier = state.get("model_tier", 0)
        model = model_factory.get(tier)
        system = system_prompt_builder()

        feedback = ""
        prior_errors = state.get("validation_errors") or []
        if prior_errors:
            feedback = (
                "\n\nYOUR PREVIOUS ATTEMPT FAILED VALIDATION:\n"
                + "\n".join(f"- {e}" for e in prior_errors)
                + "\nFix these specific problems in your output."
            )

        messages = [
            SystemMessage(content=system),
            HumanMessage(content=(
                "Extract structured food pantry information from this scraped "
                f"webpage content:\n\n{state.get('raw_markdown', '')}{feedback}"
            )),
        ]

        result = await model.ainvoke(messages)
        parsed = result["parsed"]
        raw = result["raw"]

        usage = getattr(raw, "usage_metadata", None) or {}
        cost_tracker.add_usage(
            model_for_tier(tier),
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )

        data = parsed.model_dump() if hasattr(parsed, "model_dump") else dict(parsed)
        return {"extracted_data": data, "confidence": data.get("confidence")}
    return extract_node
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_extract_node.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/nodes/extract.py backend_ml/tests/agent/test_extract_node.py
git commit -m "feat(agent): add extract node with retry feedback + cost tracking"
```

---

### Task 10: Validate node + retry/escalation logic

**Files:**
- Create: `backend_ml/agent/nodes/validate.py`
- Test: `backend_ml/tests/agent/test_validate_node.py`
- Test: `backend_ml/tests/agent/test_retry_logic.py`

- [ ] **Step 1: Write the failing validate-node test.**

```python
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
```

- [ ] **Step 2: Write the failing retry-logic test.**

```python
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


def test_bump_retry_increments_count_and_tier():
    out = bump_retry({"retry_count": 0, "model_tier": 0})
    assert out["retry_count"] == 1 and out["model_tier"] == 1
```

- [ ] **Step 3: Run both to verify they fail.**

Run: `cd backend_ml && python -m pytest tests/agent/test_validate_node.py tests/agent/test_retry_logic.py -v`
Expected: FAIL — module not found.

- [ ] **Step 4: Write `validate.py`.**

```python
# backend_ml/agent/nodes/validate.py
"""Validate node + retry/escalation edge logic.

Reuses services/validator.validate_extraction so validation rules are not
duplicated.
"""

from agent.config import CONFIDENCE_THRESHOLD, MAX_RETRIES
from agent.state import ExtractionState
from services.validator import validate_extraction, ValidationError


async def validate_node(state: ExtractionState) -> dict:
    data = state.get("extracted_data") or {}
    try:
        validate_extraction(data)
        return {"validation_errors": []}
    except ValidationError as e:
        return {"validation_errors": [f"{e.field}: {e.reason}"]}


def should_retry(state: ExtractionState) -> str:
    has_errors = bool(state.get("validation_errors"))
    low_conf = (state.get("confidence") or 0) < CONFIDENCE_THRESHOLD
    if (has_errors or low_conf) and state.get("retry_count", 0) < MAX_RETRIES:
        return "retry"
    return "done"


def bump_retry(state: ExtractionState) -> dict:
    new_count = state.get("retry_count", 0) + 1
    return {"retry_count": new_count, "model_tier": new_count}
```

- [ ] **Step 5: Run to verify both pass.**

Run: `cd backend_ml && python -m pytest tests/agent/test_validate_node.py tests/agent/test_retry_logic.py -v`
Expected: 7 PASS.

- [ ] **Step 6: Commit.**

```bash
git add backend_ml/agent/nodes/validate.py backend_ml/tests/agent/test_validate_node.py backend_ml/tests/agent/test_retry_logic.py
git commit -m "feat(agent): add validate node + should_retry/bump_retry edge logic"
```

---

### Task 11: Persist node

**Files:**
- Create: `backend_ml/agent/nodes/persist.py`
- Test: `backend_ml/tests/agent/test_persist_node.py`

- [ ] **Step 1: Write the failing test** (uses the `test_db` fixture).

```python
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
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_persist_node.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `persist.py`.**

```python
# backend_ml/agent/nodes/persist.py
"""Persist node — update an existing pantry's dynamic fields after a refresh.

Identity fields (name/address/lat/lng/city/state) are preserved; only the
LLM-extracted dynamic fields + freshness metadata are written. If the final
attempt is still invalid, we DO NOT write — refusing to clobber good existing
data with a bad extraction.
"""

from datetime import datetime, timezone
from agent.state import ExtractionState


def make_persist_node(db=None):
    def _collection():
        if db is not None:
            return db["pantries"]
        from database import get_collection
        return get_collection("pantries")

    async def persist_node(state: ExtractionState) -> dict:
        if state.get("validation_errors"):
            return {"outcome": "failed", "final_update": None}

        data = state["extracted_data"]
        update = {
            "status": data["status"],
            "hours_notes": data["hours_notes"],
            "hours_today": data["hours_today"],
            "eligibility_rules": data["eligibility_rules"],
            "is_id_required": data["is_id_required"],
            "residency_req": data.get("residency_req"),
            "special_notes": data.get("special_notes"),
            "confidence": data["confidence"],
            "last_updated": datetime.now(timezone.utc),
            "scraped_at": datetime.now(timezone.utc),
            "scrape_method": "crawl4ai",
        }
        await _collection().update_one(
            {"source_url": state["source_url"]}, {"$set": update}
        )
        return {"outcome": "success", "final_update": update}
    return persist_node
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_persist_node.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/nodes/persist.py backend_ml/tests/agent/test_persist_node.py
git commit -m "feat(agent): add persist node (dynamic-field update, no clobber on failure)"
```

---

### Task 12: Assemble + compile the extraction subgraph; integration-test against fixtures

**Files:**
- Create: `backend_ml/agent/subgraph.py`
- Test: `backend_ml/tests/agent/test_extraction_subgraph.py`

- [ ] **Step 1: Write `subgraph.py`.**

```python
# backend_ml/agent/subgraph.py
"""Assemble the per-source extraction subgraph:

    scrape → extract → validate → should_retry? ─ retry → bump_retry → extract
                                                └ done  → persist → END
"""

from langgraph.graph import StateGraph, START, END
from agent.state import ExtractionState
from agent.nodes.scrape import make_scrape_node
from agent.nodes.extract import make_extract_node
from agent.nodes.validate import validate_node, should_retry, bump_retry
from agent.nodes.persist import make_persist_node


def build_extraction_subgraph(scraper, model_factory, cost_tracker,
                              system_prompt_builder, db=None):
    g = StateGraph(ExtractionState)
    g.add_node("scrape", make_scrape_node(scraper))
    g.add_node("extract", make_extract_node(model_factory, cost_tracker, system_prompt_builder))
    g.add_node("validate", validate_node)
    g.add_node("bump_retry", bump_retry)
    g.add_node("persist", make_persist_node(db=db))

    g.add_edge(START, "scrape")
    g.add_edge("scrape", "extract")
    g.add_edge("extract", "validate")
    g.add_conditional_edges("validate", should_retry,
                            {"retry": "bump_retry", "done": "persist"})
    g.add_edge("bump_retry", "extract")
    g.add_edge("persist", END)
    return g.compile()
```

- [ ] **Step 2: Write the failing integration test** against all 5 fixtures (LLM faked from `expected_outputs`, scraper faked from fixture markdown).

```python
# backend_ml/tests/agent/test_extraction_subgraph.py
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


async def test_subgraph_persists_each_fixture(test_db):
    for name in NAMES:
        await test_db["pantries"].insert_one({
            "name": name, "address": "a", "lat": 1.0, "lng": 2.0,
            "hours_notes": "OLD", "status": "UNKNOWN",
            "source_url": f"https://{name}.org",
            "last_updated": "2020-01-01T00:00:00Z",
        })
        expected = _expected(name)
        model = FakeStructuredModel(scripted=[ExtractionResult(**{
            k: expected[k] for k in ExtractionResult.model_fields
        })])
        factory = FakeModelFactory([model])
        markdown = (FIX / f"{name}.md").read_text()
        app = build_extraction_subgraph(
            FakeScraper(markdown=markdown), factory, CostTracker(1.0),
            lambda: "SYS", db=test_db,
        )
        final = await app.ainvoke({
            "source_url": f"https://{name}.org", "model_tier": 0,
            "retry_count": 0, "validation_errors": [],
        })
        assert final["outcome"] == "success"
        doc = await test_db["pantries"].find_one({"source_url": f"https://{name}.org"})
        assert doc["confidence"] == expected["confidence"]
        assert doc["status"] == expected["status"]


async def test_subgraph_retries_then_succeeds(test_db):
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
```

- [ ] **Step 3: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_extraction_subgraph.py -v`
Expected: FAIL — `agent.subgraph` not found (if you wrote Step 1 first, the test fails on assertions only until the graph wiring is correct).

- [ ] **Step 4: Make it pass.** If any fixture's `expected_outputs` field set doesn't cover all `ExtractionResult.model_fields`, fill missing optional fields with `None` in the test's dict comprehension (use `expected.get(k)`). Adjust the comprehension to:

```python
ExtractionResult(**{k: expected.get(k) for k in ExtractionResult.model_fields})
```

- [ ] **Step 5: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_extraction_subgraph.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit.**

```bash
git add backend_ml/agent/subgraph.py backend_ml/tests/agent/test_extraction_subgraph.py
git commit -m "feat(agent): assemble extraction subgraph + fixture integration tests"
```

---

## Phase 2 — Metrics & source loading

### Task 13: `source_metrics` update node

**Files:**
- Create: `backend_ml/agent/nodes/metrics.py`
- Test: `backend_ml/tests/agent/test_metrics.py`

- [ ] **Step 1: Write the failing test.**

```python
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
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_metrics.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `metrics.py`.**

```python
# backend_ml/agent/nodes/metrics.py
"""Update node — write per-source metrics after a run.

One atomic upsert per processed source. Running averages and rates are
recomputed from the post-increment totals.
"""

from datetime import datetime, timezone
from urllib.parse import urlparse
from agent.state import ParentState


def make_update_metrics_node(db=None):
    def _collection():
        if db is not None:
            return db["source_metrics"]
        from database import get_collection
        return get_collection("source_metrics")

    async def update_metrics_node(state: ParentState) -> dict:
        col = _collection()
        now = datetime.now(timezone.utc)
        for r in state.get("results", []):
            url = r["source_url"]
            success = r["outcome"] == "success"
            existing = await col.find_one({"source_url": url}) or {}

            total_runs = existing.get("total_runs", 0) + 1
            successes = existing.get("successes", 0) + (1 if success else 0)
            failures = existing.get("failures", 0) + (0 if success else 1)
            val_errors = existing.get("_validation_errors", 0) + (
                1 if r.get("had_validation_error") else 0)
            prev_avg = existing.get("avg_latency_ms", 0.0)
            prev_n = existing.get("total_runs", 0)
            avg_latency = (prev_avg * prev_n + r.get("latency_ms", 0.0)) / total_runs
            consecutive = 0 if success else existing.get("consecutive_failures", 0) + 1

            doc = {
                "source_url": url,
                "domain": urlparse(url).netloc,
                "total_runs": total_runs,
                "successes": successes,
                "failures": failures,
                "_validation_errors": val_errors,
                "success_rate": successes / total_runs,
                "validation_error_rate": val_errors / total_runs,
                "avg_latency_ms": round(avg_latency, 2),
                "consecutive_failures": consecutive,
                "last_scraped": now,
                "last_model_used": str(r.get("model_tier")),
            }
            if success:
                doc["last_success"] = now
            else:
                doc["last_error"] = r.get("reason", "unknown")

            await col.update_one({"source_url": url}, {"$set": doc}, upsert=True)
        return {}
    return update_metrics_node
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_metrics.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Add the unique index** to `database.py` `connect_to_mongo()` (append after the discovery_cache TTL index block):

```python
    # Unique index on source_metrics.source_url
    await db["source_metrics"].create_index(
        [("source_url", 1)], name="source_metrics_url_unique", unique=True,
    )
```

- [ ] **Step 6: Commit.**

```bash
git add backend_ml/agent/nodes/metrics.py backend_ml/tests/agent/test_metrics.py backend_ml/database.py
git commit -m "feat(agent): add source_metrics update node + unique index"
```

---

### Task 14: `load_sources` node

**Files:**
- Create: `backend_ml/agent/nodes/load_sources.py`
- Test: `backend_ml/tests/agent/test_load_sources.py`

- [ ] **Step 1: Write the failing test.**

```python
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
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_load_sources.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `load_sources.py`.**

```python
# backend_ml/agent/nodes/load_sources.py
"""Load node — find stale pantries with a source_url and join their metrics."""

from datetime import datetime, timezone, timedelta
from agent.config import FRESHNESS_FLOOR_HOURS
from agent.state import ParentState


def make_load_sources_node(db=None):
    def _db():
        if db is not None:
            return db
        from database import get_database
        return get_database()

    async def load_sources_node(state: ParentState) -> dict:
        database = _db()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_FLOOR_HOURS)

        candidates = []
        cursor = database["pantries"].find({
            "source_url": {"$exists": True, "$nin": [None, ""]},
            "last_updated": {"$lt": cutoff},
        })
        async for doc in cursor:
            candidates.append({
                "pantry_id": str(doc["_id"]),
                "source_url": doc["source_url"],
                "name": doc.get("name"),
                "city": doc.get("city"),
                "state": doc.get("state"),
                "last_updated": doc.get("last_updated"),
            })

        # Join metrics
        metrics = {}
        async for m in database["source_metrics"].find({}):
            metrics[m["source_url"]] = m
        for c in candidates:
            m = metrics.get(c["source_url"], {})
            c["consecutive_failures"] = m.get("consecutive_failures", 0)
            c["success_rate"] = m.get("success_rate", None)
            c["avg_latency_ms"] = m.get("avg_latency_ms", None)

        return {"candidate_sources": candidates}
    return load_sources_node
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_load_sources.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/nodes/load_sources.py backend_ml/tests/agent/test_load_sources.py
git commit -m "feat(agent): add load_sources node (stale pantries + metrics join)"
```

---

## Phase 3 — Curator & parent graph

### Task 15: Curator node

**Files:**
- Create: `backend_ml/agent/nodes/curator.py`
- Test: `backend_ml/tests/agent/test_curator.py`

- [ ] **Step 1: Write the failing test.** The deterministic parts (quarantine, fallback staleness sort, selection cap) are tested without an LLM by injecting a fake ranker.

```python
# backend_ml/tests/agent/test_curator.py
from datetime import datetime, timezone, timedelta
from agent.nodes.curator import make_curator_node, quarantine_and_prefilter

now = datetime.now(timezone.utc)


def _cand(url, hours_old, consec=0):
    return {"source_url": url, "pantry_id": url, "city": "Atlanta",
            "last_updated": now - timedelta(hours=hours_old),
            "consecutive_failures": consec, "success_rate": None}


def test_quarantine_excludes_chronic_failures():
    cands = [_cand("a", 48, consec=6), _cand("b", 48, consec=2)]
    kept, quarantined = quarantine_and_prefilter(cands)
    assert [c["source_url"] for c in kept] == ["b"]
    assert [c["source_url"] for c in quarantined] == ["a"]


async def test_curator_cold_start_sorts_by_staleness(test_db=None):
    cands = [_cand("new", 25), _cand("old", 100), _cand("mid", 50)]
    # ranker=None → deterministic staleness fallback
    node = make_curator_node(ranker=None)
    out = await node({"candidate_sources": cands})
    assert [c["source_url"] for c in out["selected_sources"]] == ["old", "mid", "new"]


async def test_curator_respects_max_sources(monkeypatch):
    import agent.nodes.curator as mod
    monkeypatch.setattr(mod, "MAX_SOURCES_PER_RUN", 2)
    cands = [_cand("a", 100), _cand("b", 90), _cand("c", 80)]
    node = make_curator_node(ranker=None)
    out = await node({"candidate_sources": cands})
    assert len(out["selected_sources"]) == 2
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_curator.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `curator.py`.**

```python
# backend_ml/agent/nodes/curator.py
"""Curator node — quarantine chronic failures, then rank/select stale sources.

An optional `ranker` callable (the LLM path) reorders candidates and returns a
reasoning string. When `ranker` is None (or fails), we fall back to a
deterministic staleness-first ordering. Either way, selection is capped at
MAX_SOURCES_PER_RUN.
"""

import logging
from agent.config import MAX_SOURCES_PER_RUN, QUARANTINE_THRESHOLD
from agent.state import ParentState

logger = logging.getLogger("equitable")


def quarantine_and_prefilter(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    kept, quarantined = [], []
    for c in candidates:
        if c.get("consecutive_failures", 0) > QUARANTINE_THRESHOLD:
            quarantined.append(c)
        else:
            kept.append(c)
    return kept, quarantined


def _staleness_sort(candidates: list[dict]) -> list[dict]:
    # Oldest last_updated first; None sorts oldest.
    return sorted(candidates, key=lambda c: (c.get("last_updated") is not None,
                                             c.get("last_updated")))


def make_curator_node(ranker=None):
    async def curator_node(state: ParentState) -> dict:
        candidates = state.get("candidate_sources", [])
        kept, quarantined = quarantine_and_prefilter(candidates)

        reasoning = "deterministic staleness ordering (no ranker / cold start)"
        ordered = _staleness_sort(kept)

        if ranker is not None and kept:
            try:
                ordered, reasoning = await ranker(kept)
            except Exception as e:  # fall back, never crash the run
                logger.warning("Curator ranker failed; using staleness fallback",
                               extra={"event": "curator_fallback", "error": str(e)})
                ordered = _staleness_sort(kept)

        selected = ordered[:MAX_SOURCES_PER_RUN]
        logger.info("Curator selected sources",
                    extra={"event": "curator_select", "selected": len(selected),
                           "quarantined": len(quarantined)})
        return {"selected_sources": selected, "quarantined": quarantined,
                "curator_reasoning": reasoning}
    return curator_node
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_curator.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/nodes/curator.py backend_ml/tests/agent/test_curator.py
git commit -m "feat(agent): add curator node (quarantine + staleness/LLM ranking + cap)"
```

---

### Task 16: LLM ranker for the curator

**Files:**
- Modify: `backend_ml/agent/nodes/curator.py`
- Test: `backend_ml/tests/agent/test_curator.py` (append)

- [ ] **Step 1: Append a failing test** for the LLM ranker builder (LLM faked).

```python
# append to backend_ml/tests/agent/test_curator.py
from agent.nodes.curator import make_llm_ranker


class _FakeChat:
    async def ainvoke(self, messages):
        class M:
            content = '{"selected": ["old", "new"], "reasoning": "freshness first"}'
        return M()


async def test_llm_ranker_orders_by_returned_list():
    cands = [_cand("new", 25), _cand("old", 100)]
    ranker = make_llm_ranker(_FakeChat())
    ordered, reasoning = await ranker(cands)
    assert [c["source_url"] for c in ordered] == ["old", "new"]
    assert "freshness" in reasoning
```

- [ ] **Step 2: Run to verify it fails.**

Run: `cd backend_ml && python -m pytest tests/agent/test_curator.py::test_llm_ranker_orders_by_returned_list -v`
Expected: FAIL — `make_llm_ranker` not defined.

- [ ] **Step 3: Append `make_llm_ranker` to `curator.py`.**

```python
# append to backend_ml/agent/nodes/curator.py
import json


def make_llm_ranker(chat_model):
    """Returns an async ranker(candidates) -> (ordered_list, reasoning).

    `chat_model` is a LangChain chat model (curator tier). It returns JSON
    {"selected": [source_url,...], "reasoning": "..."}; we reorder candidates
    to match and append any the LLM omitted (by staleness) so nothing is lost.
    """
    from langchain_core.messages import HumanMessage

    async def ranker(candidates):
        summary = [
            {"source_url": c["source_url"], "city": c.get("city"),
             "hours_stale": None if not c.get("last_updated") else "stale",
             "success_rate": c.get("success_rate"),
             "consecutive_failures": c.get("consecutive_failures", 0)}
            for c in candidates
        ]
        prompt = (
            "You are a data-refresh curator. Given these food-pantry sources and "
            "their reliability metrics, return the order to refresh them this run. "
            "Prioritize staleness, reliability (higher success_rate), and city "
            "diversity. Respond ONLY with JSON: "
            '{"selected": [source_url, ...], "reasoning": "..."}\n\n'
            f"{json.dumps(summary, default=str)}"
        )
        resp = await chat_model.ainvoke([HumanMessage(content=prompt)])
        text = resp.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        parsed = json.loads(text)
        by_url = {c["source_url"]: c for c in candidates}
        ordered = [by_url[u] for u in parsed["selected"] if u in by_url]
        # append anything the LLM dropped, staleness-first
        missing = [c for c in candidates if c["source_url"] not in parsed["selected"]]
        ordered += _staleness_sort(missing)
        return ordered, parsed.get("reasoning", "")
    return ranker
```

- [ ] **Step 4: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_curator.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/nodes/curator.py backend_ml/tests/agent/test_curator.py
git commit -m "feat(agent): add LLM ranker for curator with staleness fallback"
```

---

### Task 17: Aggregate node + parent graph (fan-out + budget gate)

**Files:**
- Create: `backend_ml/agent/nodes/aggregate.py`
- Create: `backend_ml/agent/graph.py`
- Test: `backend_ml/tests/agent/test_graph.py`

- [ ] **Step 1: Write `aggregate.py`.**

```python
# backend_ml/agent/nodes/aggregate.py
"""Aggregate node — build a run summary from per-source results."""

from agent.state import ParentState


async def aggregate_report_node(state: ParentState) -> dict:
    results = state.get("results", [])
    summary = {
        "selected": len(state.get("selected_sources", [])),
        "processed": len(results),
        "succeeded": sum(1 for r in results if r["outcome"] == "success"),
        "failed": sum(1 for r in results if r["outcome"] == "failed"),
        "skipped_budget": sum(1 for r in results if r["outcome"] == "skipped_budget"),
        "cost_spent_usd": round(state.get("cost_spent_usd", 0.0), 4),
        "quarantined": len(state.get("quarantined", [])),
    }
    import logging
    logging.getLogger("equitable").info(
        "Refresh run summary", extra={"event": "refresh_summary", **summary})
    return {"results": results}  # passthrough; summary is logged
```

- [ ] **Step 2: Write `graph.py`** — the parent graph. `process_sources` does the semaphore-bounded fan-out and enforces the cost budget (it invokes the prebuilt extraction subgraph per source).

```python
# backend_ml/agent/graph.py
"""Assemble the parent refresh graph:

    load_sources → curator → process_sources → aggregate_report → update_metrics
"""

import asyncio
from langgraph.graph import StateGraph, START, END
from agent.config import MAX_CONCURRENT
from agent.state import ParentState
from agent.nodes.aggregate import aggregate_report_node


def make_process_sources_node(subgraph, cost_tracker):
    """Fan out over selected sources under a semaphore, gated by the budget."""
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def _run_one(src):
        async with sem:
            if cost_tracker.is_exhausted:
                return {"source_url": src["source_url"], "outcome": "skipped_budget",
                        "latency_ms": 0.0, "model_tier": None,
                        "had_validation_error": False}
            final = await subgraph.ainvoke({
                "source_url": src["source_url"],
                "pantry_id": src.get("pantry_id", ""),
                "model_tier": 0, "retry_count": 0, "validation_errors": [],
            })
            return {
                "source_url": src["source_url"],
                "outcome": final.get("outcome", "failed"),
                "latency_ms": final.get("latency_ms", 0.0),
                "model_tier": final.get("model_tier", 0),
                "had_validation_error": bool(final.get("validation_errors")),
            }

    async def process_sources_node(state: ParentState) -> dict:
        selected = state.get("selected_sources", [])
        results = await asyncio.gather(*[_run_one(s) for s in selected])
        return {"results": list(results), "cost_spent_usd": cost_tracker.spent_usd}

    return process_sources_node


def build_refresh_graph(load_node, curator_node, subgraph, cost_tracker,
                        update_metrics_node, checkpointer=None):
    g = StateGraph(ParentState)
    g.add_node("load_sources", load_node)
    g.add_node("curator", curator_node)
    g.add_node("process_sources", make_process_sources_node(subgraph, cost_tracker))
    g.add_node("aggregate_report", aggregate_report_node)
    g.add_node("update_metrics", update_metrics_node)

    g.add_edge(START, "load_sources")
    g.add_edge("load_sources", "curator")
    g.add_edge("curator", "process_sources")
    g.add_edge("process_sources", "aggregate_report")
    g.add_edge("aggregate_report", "update_metrics")
    g.add_edge("update_metrics", END)
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 3: Write the failing test** wiring real nodes + fakes against `test_db`, including a budget-exhaustion case.

```python
# backend_ml/tests/agent/test_graph.py
from datetime import datetime, timezone, timedelta
from agent.cost import CostTracker
from agent.subgraph import build_extraction_subgraph
from agent.graph import build_refresh_graph
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.curator import make_curator_node
from agent.nodes.metrics import make_update_metrics_node
from agent.state import ExtractionResult
from tests.agent.conftest import FakeStructuredModel, FakeModelFactory, FakeScraper

GOOD = {"status": "OPEN", "hours_notes": "x", "hours_today": "x",
        "eligibility_rules": ["Open to all"], "is_id_required": False,
        "residency_req": None, "special_notes": None, "confidence": 8}


def _factory():
    return FakeModelFactory([FakeStructuredModel(scripted=[ExtractionResult(**GOOD)])])


async def _seed(test_db, n):
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    for i in range(n):
        await test_db["pantries"].insert_one(
            {"name": f"p{i}", "address": "a", "lat": 1, "lng": 2, "hours_notes": "OLD",
             "status": "UNKNOWN", "source_url": f"https://p{i}.org", "last_updated": old})


async def test_refresh_graph_end_to_end(test_db):
    await _seed(test_db, 3)
    tracker = CostTracker(budget_usd=1.0)
    sub = build_extraction_subgraph(FakeScraper(), _factory(), tracker, lambda: "SYS", db=test_db)
    app = build_refresh_graph(
        make_load_sources_node(db=test_db), make_curator_node(ranker=None),
        sub, tracker, make_update_metrics_node(db=test_db))
    final = await app.ainvoke({"run_id": "t1", "cost_budget_usd": 1.0})
    assert final["results"]
    assert all(r["outcome"] == "success" for r in final["results"])
    # metrics written
    assert await test_db["source_metrics"].count_documents({}) == 3


async def test_budget_exhaustion_skips_remaining(test_db):
    await _seed(test_db, 3)
    tracker = CostTracker(budget_usd=0.0)   # already exhausted
    sub = build_extraction_subgraph(FakeScraper(), _factory(), tracker, lambda: "SYS", db=test_db)
    app = build_refresh_graph(
        make_load_sources_node(db=test_db), make_curator_node(ranker=None),
        sub, tracker, make_update_metrics_node(db=test_db))
    final = await app.ainvoke({"run_id": "t2", "cost_budget_usd": 0.0})
    assert all(r["outcome"] == "skipped_budget" for r in final["results"])
```

- [ ] **Step 4: Run to verify it fails, then passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_graph.py -v`
Expected: after writing Steps 1–2, 2 PASS.

- [ ] **Step 5: Commit.**

```bash
git add backend_ml/agent/nodes/aggregate.py backend_ml/agent/graph.py backend_ml/tests/agent/test_graph.py
git commit -m "feat(agent): assemble parent refresh graph with budget-gated fan-out"
```

---

## Phase 4 — Checkpointer

### Task 18: MongoDB checkpointer + resume test

**Files:**
- Create: `backend_ml/agent/checkpointer.py`
- Test: `backend_ml/tests/agent/test_checkpointer.py`

- [ ] **Step 1: Write `checkpointer.py`.**

```python
# backend_ml/agent/checkpointer.py
"""MongoDB-backed LangGraph checkpointer for durable, resumable runs."""

import os
from contextlib import asynccontextmanager


@asynccontextmanager
async def mongo_checkpointer(uri: str = None, db_name: str = "equitable"):
    """Yield an AsyncMongoDBSaver bound to Atlas.

    Usage:
        async with mongo_checkpointer() as cp:
            app = build_refresh_graph(..., checkpointer=cp)
            await app.ainvoke(state, {"configurable": {"thread_id": run_id}})
    """
    from langgraph.checkpoint.mongodb.aio import AsyncMongoDBSaver

    uri = uri or os.getenv("MONGO_URI")
    async with AsyncMongoDBSaver.from_conn_string(uri, db_name=db_name) as saver:
        yield saver
```

- [ ] **Step 2: Write the resume test.** A run that "crashes" mid-fan-out (one source raises) leaves a checkpoint; re-invoking with the same `thread_id` does not reprocess already-persisted sources.

```python
# backend_ml/tests/agent/test_checkpointer.py
import os
from datetime import datetime, timezone, timedelta

from agent.checkpointer import mongo_checkpointer
from agent.cost import CostTracker
from agent.subgraph import build_extraction_subgraph
from agent.graph import build_refresh_graph
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.curator import make_curator_node
from agent.nodes.metrics import make_update_metrics_node
from agent.state import ExtractionResult
from tests.agent.conftest import FakeStructuredModel, FakeModelFactory, FakeScraper

GOOD = {"status": "OPEN", "hours_notes": "x", "hours_today": "x",
        "eligibility_rules": ["Open to all"], "is_id_required": False,
        "residency_req": None, "special_notes": None, "confidence": 8}


async def test_resume_does_not_reprocess(test_db):
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    await test_db["pantries"].insert_one(
        {"name": "p", "address": "a", "lat": 1, "lng": 2, "hours_notes": "OLD",
         "status": "UNKNOWN", "source_url": "https://p.org", "last_updated": old})

    factory = FakeModelFactory([FakeStructuredModel(scripted=[ExtractionResult(**GOOD)])])
    tracker = CostTracker(1.0)
    sub = build_extraction_subgraph(FakeScraper(), factory, tracker, lambda: "SYS", db=test_db)

    async with mongo_checkpointer(uri=os.getenv("MONGO_URI"), db_name="equitable_test") as cp:
        app = build_refresh_graph(
            make_load_sources_node(db=test_db), make_curator_node(ranker=None),
            sub, tracker, make_update_metrics_node(db=test_db), checkpointer=cp)
        cfg = {"configurable": {"thread_id": "resume-test"}}
        final = await app.ainvoke({"run_id": "resume-test", "cost_budget_usd": 1.0}, cfg)
        assert final["results"][0]["outcome"] == "success"

        # Re-invoke with the same thread_id → state is restored, run is complete.
        state = await app.aget_state(cfg)
        assert state.values["results"][0]["outcome"] == "success"
```

- [ ] **Step 3: Run to verify it passes.**

Run: `cd backend_ml && python -m pytest tests/agent/test_checkpointer.py -v`
Expected: PASS. (If `langgraph.checkpoint.mongodb.aio` import path differs by version, check `python -c "import langgraph_checkpoint_mongodb; print(dir(langgraph_checkpoint_mongodb))"` and adjust the import in `checkpointer.py`.)

- [ ] **Step 4: Commit.**

```bash
git add backend_ml/agent/checkpointer.py backend_ml/tests/agent/test_checkpointer.py
git commit -m "feat(agent): add MongoDB checkpointer + resume test"
```

---

## Phase 5 — CLI & smoke

### Task 19: CLI entrypoint + end-to-end smoke

**Files:**
- Create: `backend_ml/agent/cli.py`
- Create: `backend_ml/agent/refresh.py` (so `python -m agent.refresh` works)
- Test: `backend_ml/tests/agent/test_smoke_refresh.py`

- [ ] **Step 1: Write `cli.py`** — wires real dependencies (real `ScraperService`, real `ModelFactory`, real DB, checkpointer, LangSmith).

```python
# backend_ml/agent/cli.py
"""Entrypoint for the refresh job: `python -m agent.refresh`."""

import asyncio
import logging
import os
import uuid

from agent.config import MAX_COST_USD, CURATOR_MODEL, setup_langsmith
from agent.cost import CostTracker
from agent.models import ModelFactory
from agent.prompts import build_extraction_system_prompt
from agent.subgraph import build_extraction_subgraph
from agent.graph import build_refresh_graph
from agent.checkpointer import mongo_checkpointer
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.curator import make_curator_node, make_llm_ranker
from agent.nodes.metrics import make_update_metrics_node

logger = logging.getLogger("equitable")


async def run_refresh(db_name: str = None):
    setup_langsmith()
    from database import connect_to_mongo, close_mongo_connection, get_database
    await connect_to_mongo()

    run_id = str(uuid.uuid4())
    cost_tracker = CostTracker(budget_usd=MAX_COST_USD)

    # Curator ranker (LLM, cheapest tier)
    from langchain_google_genai import ChatGoogleGenerativeAI
    curator_chat = ChatGoogleGenerativeAI(
        model=CURATOR_MODEL, temperature=0, google_api_key=os.getenv("GEMINI_API_KEY"))

    subgraph = build_extraction_subgraph(
        scraper=__import__("services.scraper", fromlist=["get_scraper_service"]).get_scraper_service(),
        model_factory=ModelFactory(),
        cost_tracker=cost_tracker,
        system_prompt_builder=build_extraction_system_prompt,
    )

    async with mongo_checkpointer(db_name=db_name or os.getenv("DATABASE_NAME", "equitable")) as cp:
        app = build_refresh_graph(
            load_node=make_load_sources_node(),
            curator_node=make_curator_node(ranker=make_llm_ranker(curator_chat)),
            subgraph=subgraph,
            cost_tracker=cost_tracker,
            update_metrics_node=make_update_metrics_node(),
            checkpointer=cp,
        )
        final = await app.ainvoke(
            {"run_id": run_id, "cost_budget_usd": MAX_COST_USD},
            {"configurable": {"thread_id": run_id}},
        )

    await close_mongo_connection()
    logger.info("Refresh complete", extra={"event": "refresh_done", "run_id": run_id,
                                           "processed": len(final.get("results", []))})
    return final


def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_refresh())


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `refresh.py`** so `python -m agent.refresh` resolves.

```python
# backend_ml/agent/refresh.py
from agent.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the end-to-end smoke test** (everything real except the LLM + scraper, against `test_db`). It asserts the spec's smoke criteria: valid pantries, confidence 1–10, within budget.

```python
# backend_ml/tests/agent/test_smoke_refresh.py
from datetime import datetime, timezone, timedelta
from agent.cost import CostTracker
from agent.subgraph import build_extraction_subgraph
from agent.graph import build_refresh_graph
from agent.nodes.load_sources import make_load_sources_node
from agent.nodes.curator import make_curator_node
from agent.nodes.metrics import make_update_metrics_node
from agent.state import ExtractionResult
from tests.agent.conftest import FakeStructuredModel, FakeModelFactory, FakeScraper

GOOD = {"status": "OPEN", "hours_notes": "Mon-Fri 9-5", "hours_today": "9-5",
        "eligibility_rules": ["Open to all"], "is_id_required": False,
        "residency_req": None, "special_notes": None, "confidence": 7}


async def test_refresh_smoke(test_db):
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    for i in range(5):
        await test_db["pantries"].insert_one(
            {"name": f"p{i}", "address": "a", "lat": 1, "lng": 2, "hours_notes": "OLD",
             "status": "UNKNOWN", "source_url": f"https://p{i}.org",
             "city": "Atlanta", "state": "GA", "last_updated": old})

    tracker = CostTracker(budget_usd=1.0)
    factory = FakeModelFactory([FakeStructuredModel(scripted=[ExtractionResult(**GOOD)])])
    sub = build_extraction_subgraph(FakeScraper(), factory, tracker, lambda: "SYS", db=test_db)
    app = build_refresh_graph(
        make_load_sources_node(db=test_db), make_curator_node(ranker=None),
        sub, tracker, make_update_metrics_node(db=test_db))

    final = await app.ainvoke({"run_id": "smoke", "cost_budget_usd": 1.0})

    assert len(final["results"]) == 5
    assert all(r["outcome"] == "success" for r in final["results"])
    assert tracker.spent_usd <= 1.0
    async for doc in test_db["pantries"].find({"source_url": {"$regex": "^https://p"}}):
        assert 1 <= doc["confidence"] <= 10
        assert doc["status"] in {"OPEN", "CLOSED", "WAITLIST", "UNKNOWN"}
```

- [ ] **Step 4: Run the full agent suite.**

Run: `cd backend_ml && python -m pytest tests/agent/ -v`
Expected: all agent tests PASS.

- [ ] **Step 5: Run the whole backend suite (regression guard).**

Run: `cd backend_ml && python -m pytest tests/ -v`
Expected: all pre-existing tests still PASS alongside the new agent tests.

- [ ] **Step 6: Commit.**

```bash
git add backend_ml/agent/cli.py backend_ml/agent/refresh.py backend_ml/tests/agent/test_smoke_refresh.py
git commit -m "feat(agent): add CLI entrypoint + end-to-end refresh smoke test"
```

---

## Phase 6 — Documentation

### Task 20: Append ADRs

**Files:**
- Modify: `docs/decisions.md`

- [ ] **Step 1: Append ADR-015 through ADR-018 and ADR-020** to `docs/decisions.md` (before the "Template for New Decisions" section). Use the existing ADR format. Write the full bodies:

  - **ADR-015: Observability — LangSmith replaces Braintrust.** Context: the rebuilt agent is LangGraph-based; LangSmith auto-traces nodes/edges with zero glue. Decision: remove Braintrust auto-instrument from `main.py`; agent sets `LANGCHAIN_*` env vars, project `equitable-refresh-agent`. Consequences: live `/ingest` endpoint loses tracing (out of scope, revisit later).
  - **ADR-016: LangGraph for agent orchestration.** Context/decision: adopt LangGraph state machine + subgraphs for the refresh agent (learning-first; the live demand-driven path already covers async). Consequences: new deps; per-URL extraction is a reusable subgraph.
  - **ADR-017: Standalone scheduled refresh job + curator (multi-agent).** Context: curator needs source history, which only exists for already-stored pantries; live path is latency-sensitive. Decision: refresh job over stale DB pantries (`source_url`, >24h), curator ranks within a cost budget; live path untouched. Consequences: new `source_metrics` collection.
  - **ADR-018: Cheap-first model escalation + per-run cost budget.** Decision: extractor tier ladder Flash-Lite → 2.0 Flash → 2.5 Flash, escalating on retry (validation failure OR confidence <6); per-run `MAX_COST_USD` halts the run cleanly. Consequences: `MODEL_PRICING` must be kept current.
  - **ADR-020: MongoDB-backed LangGraph checkpointer.** Decision: persist graph state to Atlas for resume-on-crash + time-travel debugging; thread_id = run_id. Consequences: extra checkpoint collections on Atlas.

  (ADR-019, Fargate/no-NAT, is intentionally deferred to Plan 2.)

- [ ] **Step 2: Commit.**

```bash
git add docs/decisions.md
git commit -m "docs: add ADR-015..018, 020 for the LangGraph refresh agent"
```

---

## Self-Review (completed by plan author)

**Spec coverage** — every spec section maps to a task:
- §2.1 graph topology → Tasks 12 (subgraph), 17 (parent) ✓
- §2.2 should_retry / §2.3 model routing → Tasks 6, 9, 10 ✓
- §2.4 state → Task 3 ✓
- §2.5 nodes → Tasks 8–17 ✓
- §3 curator → Tasks 15–16 ✓
- §4.1 source_metrics / §4.2 checkpointer → Tasks 13, 18 ✓
- §5 cost-aware → Tasks 4, 9, 17 (budget gate). **Prompt caching is intentionally NOT a task in Plan 1** — see note below.
- §6 LangSmith → Tasks 1, 2 (`setup_langsmith`), 19 ✓
- §7 structure/deps → Tasks 1–3 ✓
- §8 candidate scope → Task 14 ✓
- §9 deployment → **Plan 2** ✓
- §10 ADRs → Task 20 (015–018, 020) + Plan 2 (019) ✓
- §11 testing → every task is TDD; fixtures in Task 12; regression guard in Tasks 1, 19 ✓
- §12 sequencing → tasks follow it ✓

**Deferred to Plan 2 (deployment):** Dockerfile, ECR/IAM/Fargate task def, public-subnet networking, EventBridge schedule, ADR-019.

**Known follow-up — prompt caching (spec §5):** Gemini context caching through the LangChain wrapper is version-sensitive and has a minimum-token threshold (the static prompt may not clear it, making caching a no-op). To keep this plan's code accurate and TDD-clean, prompt caching is **not** implemented here. It is captured as the first enhancement task in Plan 2 (or a standalone follow-up), implemented against `ChatGoogleGenerativeAI(cached_content=...)` with a guard that skips caching below the threshold. This is a cost optimization, not a correctness requirement — the agent is fully functional without it.

**Placeholder scan:** no TBD/TODO; all node code, test code, and commands are concrete.

**Type consistency:** `ExtractionResult` fields are consistent across Tasks 3/9/12; `should_retry`/`bump_retry`/`make_*_node` names match between definition and use; `results` dicts carry the same keys produced in Task 17 and consumed in Tasks 13/17.
