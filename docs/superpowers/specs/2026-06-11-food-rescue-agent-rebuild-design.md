# Spec: Food Rescue Agent Rebuild — LangGraph Refresh Pipeline

**Date**: 2026-06-11
**Status**: Approved (design) — pending implementation plan
**Author**: Planning session (brainstorming → spec)

---

## 0. Framing & Goal

**Primary goal: learning-first.** This rebuild exists to demonstrably exercise production agent-engineering patterns — LangGraph state machines, conditional/retry edges, subgraph composition, multi-agent coordination, async fan-out, cost-aware model routing, and LangSmith observability. We deliberately adopt these patterns **even where the existing async code already covers the functional need**, because demonstrable skill is the point. The one hard constraint: do not regress EquiTable's live user-facing experience.

A secondary (genuine) benefit: pantry hours/status go stale, and `docs/seed_strategy.md` already calls for a freshness policy. A scheduled refresh pipeline directly serves that need, so this is not purely a learning exercise — it moves the product forward too.

### Why a new job, not a rewrite of the live path

The existing system is already more advanced than a naive "custom sequential Python" agent:

- `services/discovery_service.py` already does async parallel scraping (`asyncio.Semaphore`, `asyncio.gather(..., return_exceptions=True)`), SSE streaming, dedup, and 7-day caching.
- The system is **demand-driven** (Google Places discovery on map pan) plus curated `seed_urls.json` — not a fixed batch of sources scraped every run.
- Observability is already wired via Braintrust (`main.py`).

What is genuinely **missing** and what this spec adds:

- **No retry loop.** `services/ingestion_pipeline.py` raises `IngestionError` on validation failure — it never loops back to re-extract.
- **No source-prioritization / curator layer.**
- **No model routing or per-run cost budget.**
- **No historical per-source metrics.**

The curator only makes sense where sources have *history* to rank on. Live-discovery URLs are brand-new (no history). A refresh job over already-stored pantries is exactly where that history lives — which is what makes the curator a real agent rather than a toy. The retry loop, curator call, and cost budget all add latency and tokens, which is acceptable in a background batch job but would harm the latency-sensitive live SSE path. Therefore the rebuilt agent lives in a **new standalone background refresh job**, and the live discovery path is left untouched.

---

## 1. Feature Summary

A standalone, scheduled background job — `backend_ml/agent/` — that re-scrapes stale pantries to keep their data fresh. It is built as a **LangGraph multi-agent state machine**:

- A **curator agent** ranks stale stored pantries by reliability, staleness, and city diversity, then selects a budget-bounded subset to refresh this run.
- An **extraction subgraph** (reusable) processes each selected source: scrape → extract → validate, with a **conditional retry edge** that feeds validation/low-confidence signals back and escalates the model.
- State is persisted via a **MongoDB-backed LangGraph checkpointer** (resume-on-crash + time-travel debugging).
- Execution is **cost-aware**: cheap-first model routing with escalation, prompt caching on the static prompt, and a per-run dollar budget that halts the run cleanly when hit.
- Everything is traced end-to-end in **LangSmith**.

It runs as a **Dockerized CLI**, deployed to **AWS ECS Fargate**, triggered **once daily by EventBridge Scheduler**.

---

## 2. Architecture

### 2.1 Graph topology

**Parent graph (the refresh job):**

```
load_sources → curator → [fan-out: extraction subgraph per selected source] → aggregate_report → update_metrics → END
```

**Extraction subgraph (reusable, one instance per source):**

```
scrape → extract → validate → should_retry?
                                 ├─ retry → extract   (feed errors back + escalate model tier)
                                 └─ done  → persist → END
```

- The extraction core is written as a **subgraph** specifically so it can later be dropped into the live discovery path without a rewrite (reusability is a deliberate design goal). The live path is NOT modified in this spec.
- Fan-out over selected sources uses `asyncio.Semaphore` to cap concurrency (default **4** concurrent subgraphs).

### 2.2 `should_retry` conditional edge

```
should_retry(state) -> "retry" | "done"
  retry  if (validation_failed OR confidence < CONFIDENCE_THRESHOLD) AND retry_count < MAX_RETRIES
  done   otherwise
```

- `CONFIDENCE_THRESHOLD = 6`
- `MAX_RETRIES = 2` (so up to **3 total attempts**)
- On `retry`: the `extract` node receives the specific `ValidationError(field, reason)` (or the low-confidence signal) injected into the prompt for self-correction, **and** the model tier escalates one rung.
- Cost note: retrying on low confidence (not just hard validation failures) can spend tokens on inherently-sparse sources that may not improve. This is an accepted tradeoff — the per-run cost budget is the backstop that prevents runaway spend.

### 2.3 Model routing (cheap-first with escalation, all-Gemini)

| Role | Attempt | Model |
|------|---------|-------|
| Curator | — | `gemini-2.0-flash-lite` |
| Extractor | 1 (initial) | `gemini-2.0-flash-lite` |
| Extractor | 2 (retry 1) | `gemini-2.0-flash` |
| Extractor | 3 (retry 2) | `gemini-2.5-flash` |

- If `gemini-2.5-flash` is unavailable on the account, the ladder falls back to `gemini-2.0-flash` for the final rung; this is a config constant, not a code change.
- Models are constructed via `langchain-google-genai` (`ChatGoogleGenerativeAI`), making the tier a one-line swap.

### 2.4 State definitions

**ParentState (TypedDict):**
```
run_id: str
candidate_sources: list[dict]      # stale pantries + joined source_metrics
selected_sources: list[str]        # curator output (source_urls)
curator_reasoning: str
results: list[dict]                # per-source outcome summaries
cost_spent_usd: float
cost_budget_usd: float
```

**ExtractionState (TypedDict, subgraph):**
```
source_url: str
pantry_id: str
raw_markdown: str | None
extracted_data: dict | None
validation_errors: list[str]
confidence: int | None
retry_count: int
model_tier: int                    # 0,1,2 → indexes the escalation ladder
cost_accumulated_usd: float
final_update: dict | None          # validated PantryUpdate payload
outcome: str                       # "success" | "failed" | "skipped_budget"
```

### 2.5 Node responsibilities

| Node | Responsibility | Reuses |
|------|----------------|--------|
| `load_sources` | Query DB for pantries with `source_url` and `last_updated` older than `FRESHNESS_FLOOR_HOURS`; join `source_metrics`. | — |
| `curator` | LLM-rank candidates by staleness + reliability + city diversity; select ≤ `MAX_SOURCES_PER_RUN` within budget; quarantine chronic failures. | new |
| `scrape` | Fetch markdown for one source. | `services/scraper.py` (`ScraperService`) |
| `extract` | LLM extraction from markdown; on retry, inject prior errors + escalate tier. | `prompts/*.md`, new LangChain Gemini call |
| `validate` | Run validation; populate `validation_errors` + `confidence`. | `services/validator.py` (`validate_extraction`) |
| `persist` | Upsert pantry doc by `source_url` (same merge semantics as discovery). | `models/pantry.py` |
| `aggregate_report` | Build run summary (counts, cost, durations). | new |
| `update_metrics` | Atomically update `source_metrics` for every processed source. | new |

The `extract` node reuses the **same** version-controlled prompt files (`backend_ml/prompts/extraction_system.md`, `extraction_examples.md`) so prompt logic stays single-sourced. `validate` reuses the existing `validate_extraction` so validation rules are not duplicated.

---

## 3. Curator agent — selection logic

**Input per candidate:** `source_url`, `name`, `city`, `state`, `last_updated`, plus joined `source_metrics` (`success_rate`, `avg_latency_ms`, `validation_error_rate`, `consecutive_failures`, `last_success`).

**Behavior:**
1. **Quarantine** sources with `consecutive_failures > QUARANTINE_THRESHOLD` (default **5**) — exclude from selection and surface them in the run report for manual review.
2. **Rank** the rest by a blend of: staleness (oldest `last_updated` first), reliability (higher `success_rate` preferred), and **city diversity** (avoid spending the whole run on one city).
3. **Select** up to `MAX_SOURCES_PER_RUN` (default **25**), stopping early if the projected cost would exceed the budget.
4. Emit a human-readable `curator_reasoning` string (logged + traced).

**Cold start:** on the first run (no `source_metrics` exist), ranking falls back to pure staleness order.

**Model:** `gemini-2.0-flash-lite` (curation is a lightweight ranking task — the cheapest tier is correct).

---

## 4. Database changes

### 4.1 New collection: `source_metrics`

Updated atomically at the end of each per-source run (in `update_metrics`).

```
SourceMetric {
  source_url:            string   # unique index
  domain:                string
  total_runs:            int
  successes:             int
  failures:              int
  success_rate:          float    # successes / total_runs
  avg_latency_ms:        float    # running average of scrape+extract duration
  validation_error_rate: float
  consecutive_failures:  int      # reset to 0 on success
  last_scraped:          datetime
  last_success:          datetime | null
  last_error:            string | null
  last_model_used:       string
}
```
- Unique index on `source_url`.

### 4.2 LangGraph checkpointer collections

- MongoDB-backed checkpointer (`langgraph-checkpoint-mongodb`) writes graph state to Atlas (its own collection(s), managed by the library).
- Enables resume-on-crash: a daily run that dies halfway resumes from the last checkpoint. Combined with idempotent upserts + the freshness floor, re-runs skip already-refreshed sources.

### 4.3 Unchanged

The `pantries` collection schema is unchanged. `persist` writes the same fields the discovery path writes (status, hours, eligibility, confidence, etc.), upserting by `source_url`.

---

## 5. Cost-aware execution

- **Per-run budget:** `MAX_COST_USD` (default **$0.50/run**), passed into ParentState.
- **Tracker (`cost.py`):** accumulates `tokens × per-model price` across the curator and every extraction attempt. Per-model prices are config constants.
- **Enforcement:** before scheduling a new source (and before each retry escalation), the orchestrator checks the budget. If the next call would exceed it, no new sources are scheduled, in-flight subgraphs are allowed to finish, and the run exits cleanly with `outcome="skipped_budget"` recorded for unprocessed sources. The cap is logged and traced.
- **Prompt caching:** the static extraction system prompt + few-shot examples are sent via Gemini context caching so repeated extractions don't re-pay for the static prefix.

---

## 6. Observability — switch to LangSmith

- **Remove** the Braintrust block from `backend_ml/main.py` (lines ~11–15).
- **Add** LangSmith env vars in the agent's entrypoint/config: `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT=equitable-refresh-agent`.
- LangGraph auto-traces every node, edge, and state transition to LangSmith with token counts, latency, and cost — no glue code.
- **Accepted consequence:** the live `/pantries/{id}/ingest` endpoint loses its Braintrust tracing (it does not use LangChain, so it won't auto-emit to LangSmith). Re-instrumenting the live path is explicitly **out of scope** for this spec and can be revisited later.
- **Prerequisite:** a LangSmith account + API key (free tier is sufficient).

---

## 7. Project structure

New package: `backend_ml/agent/`

```
agent/
  __init__.py
  config.py           # env-driven config + tunable constants
  state.py            # ParentState, ExtractionState TypedDicts
  models.py           # ChatGoogleGenerativeAI factory + escalation ladder
  cost.py             # token/cost tracking + budget enforcement
  checkpointer.py     # MongoDB checkpointer setup
  graph.py            # parent graph assembly + compile
  subgraph.py         # extraction subgraph assembly + compile
  nodes/
    __init__.py
    load_sources.py
    curator.py
    scrape.py         # wraps services/scraper.py
    extract.py        # LangChain Gemini call, loads prompts/*.md
    validate.py       # wraps services/validator.py
    persist.py
    aggregate.py
    metrics.py        # update source_metrics
  cli.py              # `python -m agent.refresh` entrypoint
```

### Tunable config constants (defaults)

| Constant | Default |
|----------|---------|
| `FRESHNESS_FLOOR_HOURS` | 24 |
| `MAX_SOURCES_PER_RUN` | 25 |
| `MAX_CONCURRENT` (Semaphore) | 4 |
| `CONFIDENCE_THRESHOLD` | 6 |
| `MAX_RETRIES` | 2 |
| `QUARANTINE_THRESHOLD` (consecutive failures) | 5 |
| `MAX_COST_USD` | 0.50 |

### Dependencies

- **Add:** `langgraph`, `langchain-core`, `langchain-google-genai`, `langgraph-checkpoint-mongodb`, `langsmith`
- **Remove:** `braintrust`

---

## 8. Candidate scope (settled)

- **Candidates** = every pantry already in the DB that has a `source_url` AND whose `last_updated` is older than `FRESHNESS_FLOOR_HOURS`, across **all cities** (both seed-sourced and discovery-sourced).
- **Onboarding brand-new URLs** (e.g., new entries in `seed_urls.json`) remains the job of the existing `scripts/seed_cities.py` — explicitly **not** part of this refresh job.

---

## 9. Deployment — AWS ECS Fargate + EventBridge

Built straight to Fargate now (cost is ~$1–2/mo; July credits make it ~$0).

1. **Dockerfile** — Python base + Chromium (Crawl4AI/Playwright browser install); entrypoint `python -m agent.refresh`.
2. **ECR** — push the image.
3. **IAM** — task execution role (ECR pull, CloudWatch Logs); task role for any AWS API needs.
4. **Fargate task definition** — **2 vCPU / 4 GB** (Chromium is memory-hungry).
5. **Networking — public subnet + `assignPublicIp=ENABLED`, NO NAT Gateway.** This is the critical cost decision: a NAT Gateway is ~$32/mo flat and would dwarf the entire job. A public subnet with a public IP gives direct outbound egress for ~$0.04/mo. (See ADR-019.)
6. **EventBridge Scheduler** — `cron(0 8 * * ? *)` (08:00 UTC daily; adjustable).
7. **Secrets** — `MONGO_URI`, `GEMINI_API_KEY`, `LANGCHAIN_API_KEY` via task env / AWS Secrets Manager.

### Cost summary

| Line item | Monthly |
|-----------|---------|
| Fargate compute (2 vCPU/4 GB, ~15 min/day) | ~$0.74 |
| EventBridge Scheduler (30 invocations) | ~$0.00003 |
| ECR storage (~1–2 GB image) | ~$0.10–0.20 |
| CloudWatch Logs | pennies |
| Public IPv4 | ~$0.04 |
| **AWS total** | **~$1–2** |
| Gemini API (separate, not AWS) | ~$0.50–1 |
| **All-in** | **~$1–3 (≈$0 with credits)** |

---

## 10. ADRs to add to `docs/decisions.md`

- **ADR-015**: Switch observability from Braintrust to LangSmith.
- **ADR-016**: Adopt LangGraph for agent orchestration (state machine + subgraphs).
- **ADR-017**: Standalone scheduled refresh job + curator (multi-agent) architecture; live path untouched.
- **ADR-018**: Cheap-first model escalation tied to the retry loop + per-run cost budget.
- **ADR-019**: ECS Fargate + EventBridge deploy; public-subnet / no-NAT-Gateway networking (cost rationale).
- **ADR-020**: MongoDB-backed LangGraph checkpointer for durable/resumable state.

---

## 11. Testing requirements

All tests live in `backend_ml/tests/` (mirroring existing structure). The existing live-API smoke suite **must stay green** — the live path is untouched.

### Unit tests
- **Curator ranking** (`test_curator.py`): stale source prioritized; high-failure source deprioritized; `consecutive_failures > QUARANTINE_THRESHOLD` → excluded + reported; cold start (no metrics) → pure staleness order; selection respects `MAX_SOURCES_PER_RUN`.
- **`should_retry` edge** (`test_retry_logic.py`): validation failure → retry; confidence < threshold → retry; `retry_count == MAX_RETRIES` → done; valid + high confidence → done.
- **Model escalation** (`test_models.py`): tier index maps to the correct model at each attempt; 2.5-unavailable fallback.
- **Cost budget** (`test_cost.py`): tracker accumulates correctly; run halts and marks remaining sources `skipped_budget` when budget would be exceeded.
- **Metrics update** (`test_metrics.py`): success increments `successes`, resets `consecutive_failures`; failure increments `failures` + `consecutive_failures`; running averages correct.

### Integration tests
- **Extraction subgraph** (`test_extraction_subgraph.py`): run the compiled subgraph end-to-end against the **5 existing fixtures** (`tests/fixtures/scraping/`: simple_static, wordpress_complex, minimal_info, outdated_info, multilingual), asserting against `expected_outputs/*.json`. The LLM is stubbed/mocked (recorded responses) so tests are deterministic and offline.
- **Retry path**: a fixture/mocked response that first fails validation then succeeds → assert the subgraph loops, escalates the tier, and persists the corrected result.
- **Checkpointer resume** (`test_checkpointer.py`): start a run, simulate a crash mid-fan-out, resume → already-processed sources are not reprocessed.

### Smoke test (extends existing suite)
- End-to-end refresh job over fixtures: completes within budget, writes valid pantry docs, all `confidence` values are 1–10 and non-null.

### Regression guard (must still pass)
- All existing tests in `tests/test_smoke.py`, `tests/test_validator.py`, `tests/test_scraper.py`, `tests/test_extractor.py`, `tests/test_discovery_*.py`, `tests/test_city_endpoints.py`.

---

## 12. Sequencing (build order)

1. **Scaffolding & deps**: `agent/` package skeleton, config, dependency add/remove, LangSmith env wiring, remove Braintrust block.
2. **Extraction subgraph**: state, nodes (`scrape`/`extract`/`validate`/`persist`), `should_retry` edge, model ladder, cost tracker. Tests against fixtures.
3. **`source_metrics`** persistence + `update_metrics` node + `load_sources`. Tests.
4. **Curator agent** + parent graph assembly + fan-out + `aggregate_report`. Tests.
5. **MongoDB checkpointer** integration + resume test.
6. **CLI entrypoint** + end-to-end smoke test.
7. **Dockerfile** + local container run.
8. **AWS infra**: ECR push, IAM, task def, public-subnet config, EventBridge schedule.
9. **ADRs** appended to `docs/decisions.md`.

---

## 13. Risks & open questions

- **Chromium on Fargate**: image size (~1–2 GB) and memory; verify the browser launches in-container before wiring the schedule. (Mitigated by 4 GB task size + a local container smoke run in step 7.)
- **Gemini 2.5 Flash access**: confirm availability on the account; fallback ladder already specified.
- **LangChain Gemini structured output**: the existing extractor uses `google.genai` native `response_schema`. The LangChain wrapper's structured-output path must reproduce the same JSON schema + `temperature=0` behavior; validate parity against fixtures during step 2.
- **Prompt caching minimums**: Gemini context caching has a minimum token threshold; confirm the static prompt clears it, otherwise caching is a no-op (not a correctness issue).
- **Checkpointer + async fan-out**: ensure the MongoDB checkpointer is configured correctly for concurrent subgraph execution under the semaphore.
