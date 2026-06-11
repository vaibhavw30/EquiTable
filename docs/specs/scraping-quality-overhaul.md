
# Feature: Scraping Quality Overhaul

**Phase**: 2 (must complete before Phase 1: Multi-City Expansion)
**Date**: 2026-02-14
**Author**: Planner + Tech Advisor Agent

---

## Problem

The current scraping pipeline has several gaps that will compound at scale:

1. **Single scraping tool dependency.** Firecrawl is the only scraper. If it fails (rate limits, downtime, anti-bot blocks), the entire pipeline fails. There is no fallback, no retry with an alternative tool.
2. **No validation layer.** LLM extraction output goes directly to the database. A hallucinated confidence score of 50 or a garbage `hours_today` value will be stored without question.
3. **No structured logging.** The pipeline uses bare `print()` statements. When a scrape fails in production, there is no structured log to diagnose why.
4. **No test fixtures.** Prompt changes are tested by eyeballing live scrape results. There is no regression suite — a prompt tweak that fixes one site can silently break five others.
5. **Confidence scores are uncalibrated.** The LLM self-reports confidence, but we have no ground truth to verify whether a "confidence: 8" extraction is actually accurate.
6. **No extraction prompt versioning.** The system prompt lives inline in `llm.py`. Changes are not tracked separately, and there are no few-shot examples to anchor the model's behavior.
7. **Synchronous scraping.** `scraper.py`'s `scrape_url` is synchronous (blocks the event loop), wrapped in a fake async method. This will bottleneck under concurrent requests.

These issues are tolerable for 15 Atlanta pantries. They become data-quality disasters at 100+ pantries across multiple cities.

---

## Proposed Solution

A modular, tested, and validated scraping pipeline with four layers:

```
URL → [Scraper (Firecrawl primary, Crawl4AI fallback)] → Markdown
Markdown → [Extractor (Gemini + versioned prompt + few-shot examples)] → Raw JSON
Raw JSON → [Validator (Pydantic + business rules)] → Validated PantryUpdate
Validated PantryUpdate → [Pipeline Orchestrator] → MongoDB
```

Each layer is independently testable, swappable, and logged per `docs/error_monitoring.md` patterns.

---

## Technology Decision: Scraping Tool Strategy

### Context

ADR-004 marked Firecrawl as "Under Re-evaluation" for Phase 2. The trigger: multi-city expansion will require >1000 scrapes/day, and Firecrawl costs $0.001/page with rate limits on the free tier. We need to decide whether to keep Firecrawl, replace it, or build a hybrid.

### Options Evaluated

| Criteria | Firecrawl (current) | Crawl4AI | Playwright (self-hosted) | Hybrid: Crawl4AI primary + Firecrawl fallback |
|---|---|---|---|---|
| **Fit** — solves our scraping needs | 4 — clean Markdown, but no fallback | 4 — LLM-optimized Markdown output, open source | 3 — raw HTML output, needs Markdown conversion step | 5 — best of both: free primary, quality fallback |
| **DX** — setup, docs, debugging | 5 — single API call | 3 — newer project, docs improving but thinner | 3 — browser automation is fiddly, verbose setup | 3 — two tools to understand, but clear separation |
| **Maturity** — community, stability | 4 — established SaaS, active development | 3 — newer (2024), growing fast, 20k+ GitHub stars | 5 — battle-tested, Microsoft-backed | 3 — hybrid is custom, but both components are proven |
| **Performance** — speed, resources | 3 — network round-trip to SaaS, ~2-5s/page | 4 — local execution, ~1-3s/page, async native | 3 — heavy (full Chromium), ~3-8s/page | 4 — fast path (Crawl4AI) for most sites, slow path only when needed |
| **Integration** — fits our async FastAPI stack | 3 — sync client, needs wrapping | 5 — async-native Python, returns Markdown directly | 4 — async API available | 4 — both have async support |
| **Cost** — at 1000+ scrapes/day | 2 — $1/day = $30/mo minimum, scales linearly | 5 — free (self-hosted) | 5 — free (self-hosted) | 4 — mostly free, Firecrawl only for ~10-20% of sites |
| **Total** | **21** | **24** | **23** | **23** |

### Detailed Analysis

**Firecrawl (keep as-is):** Clean Markdown output is its killer feature. But at $0.001/page with multi-city volumes, costs add up. The sync Python client blocks our async event loop. The free tier (500 credits/mo) is already tight for development. Keeping it as the *only* tool is unjustifiable at scale.

**Crawl4AI (replace entirely):** Open-source, async-native Python library purpose-built for LLM pipelines. Returns clean Markdown. Handles JS rendering via built-in Chromium. Key advantages: zero per-page cost, async from the ground up, and actively maintained. Key risk: newer project (2024), Cloudflare handling is less proven than Firecrawl for heavily protected sites, and requires Chromium on the deployment server.

**Playwright (replace entirely):** The most mature browser automation tool. Full JS rendering, excellent anti-bot handling. But it returns raw HTML — we'd need to build our own HTML→Markdown conversion (or use `markdownify`/`html2text`), adding a fragile step. Overkill for simple static sites. Best suited as a targeted tool, not the primary scraper.

**Hybrid — Crawl4AI primary, Firecrawl fallback:** Use Crawl4AI for all initial scrape attempts (free, async, Markdown output). If Crawl4AI fails (Cloudflare block, timeout, empty content), fall back to Firecrawl which has better anti-bot infrastructure. This gives us: free scraping for ~80-90% of sites, a proven fallback for tough sites, and no single point of failure.

### Recommendation

**Crawl4AI as the primary scraper** (score: 24/30). Not the hybrid approach — yet.

Rationale:
- Crawl4AI solves our core needs (JS rendering, Markdown output, async-native, free) with the highest total score.
- Adding Firecrawl as a fallback is sound engineering, but it adds complexity we don't need *today*. Our current site corpus (Atlanta pantries) is mostly WordPress/Squarespace/static HTML — sites Crawl4AI handles well.
- The scraper interface (`url → Optional[str]`) makes adding a fallback later trivial — it's a one-function change in `scraper.py`. We design for it now but don't build it until we have evidence of Crawl4AI failure rates.
- Firecrawl remains available as a manual fallback (the API key is already configured). If Crawl4AI fails on >15% of sites during multi-city seeding, we promote the hybrid approach via a follow-up ADR.

**Migration path:** Replace the Firecrawl client in `scraper.py` with Crawl4AI. Keep the same interface. Firecrawl dependency stays in `requirements.txt` but is no longer imported at startup. See ADR-008 appended to `docs/decisions.md`.

### Risks

- Crawl4AI requires Chromium on the deployment server (Render). Render's free tier supports this but adds ~200MB to the image. If this becomes an issue, we can use Crawl4AI's remote browser option or fall back to Firecrawl.
- Crawl4AI is newer — API may have breaking changes. Pin to a specific version.
- Some pantry sites behind heavy Cloudflare protection may fail. Monitor failure rates and promote hybrid approach if needed.

---

## API Contract

No new endpoints. The existing `POST /pantries/{pantry_id}/ingest` contract is unchanged.

Internal refactoring only — the pipeline layers are backend implementation details:

```python
# New internal interface (not HTTP-facing)
class ScraperService:
    async def scrape_url(self, url: str) -> Optional[str]:
        """Returns Markdown or None. Async-native."""

class ExtractorService:
    async def extract(self, markdown: str) -> Optional[dict]:
        """Returns raw extraction dict or None."""

class ValidatorService:
    def validate(self, data: dict) -> PantryUpdate:
        """Returns validated PantryUpdate or raises ValidationError."""

class IngestionPipeline:
    async def ingest(self, url: str) -> PantryUpdate:
        """Orchestrates scrape → extract → validate. Raises on failure."""
```

---

## Database Changes

None. The `pantries` collection schema and `PantryUpdate` fields remain identical.

---

## Data Flow

Step-by-step for `POST /pantries/{pantry_id}/ingest`:

1. **Request received** → `main.py` validates pantry exists in DB
2. **Scrape** → `scraper.py` calls Crawl4AI with the URL
   - Log: `{"event": "scrape_start", "url": "...", "tool": "crawl4ai"}`
   - On success: returns Markdown string
   - On failure: log error, raise `ScrapeError`
3. **Extract** → `extractor.py` sends Markdown + versioned system prompt to Gemini
   - System prompt loaded from `backend_ml/prompts/extraction_system.md`
   - Few-shot examples loaded from `backend_ml/prompts/extraction_examples.md`
   - Log: `{"event": "extraction_complete", "confidence": N}`
4. **Validate** → `validator.py` checks business rules on the raw extraction dict
   - Confidence 1-10
   - Status is valid enum
   - Name is non-empty
   - hours_today is parseable or null
   - Coordinates within city bounds (if available)
   - last_updated not in future
   - On failure: log warning, raise `ValidationError`
5. **Store** → Pipeline merges validated `PantryUpdate` into the pantry document
   - Adds `source_url` and `last_updated`
   - Log: `{"event": "scrape_complete", "url": "...", "confidence": N, "duration_ms": X}`
6. **Response** → Returns updated `Pantry` object (unchanged shape)

---

## Component Tree

No frontend changes in this phase. This is a backend-only refactor.

---

## File Changes

### New Files

```
backend_ml/
├── services/
│   ├── extractor.py            # NEW — Gemini extraction (extracted from llm.py)
│   ├── validator.py            # NEW — Post-extraction validation rules
│   └── ingestion_pipeline.py   # NEW — Orchestrator: scrape → extract → validate → store
├── prompts/
│   ├── extraction_system.md    # NEW — Versioned system prompt (moved from llm.py inline string)
│   └── extraction_examples.md  # NEW — Few-shot examples for extraction prompt
├── tests/
│   ├── fixtures/
│   │   └── scraping/
│   │       ├── simple_static.md
│   │       ├── wordpress_complex.md
│   │       ├── minimal_info.md
│   │       ├── outdated_info.md
│   │       ├── multilingual.md
│   │       └── expected_outputs/
│   │           ├── simple_static.json
│   │           ├── wordpress_complex.json
│   │           ├── minimal_info.json
│   │           ├── outdated_info.json
│   │           └── multilingual.json
│   ├── test_scraper.py         # NEW — Scraper tests (mocked HTTP)
│   ├── test_extractor.py       # NEW — Extraction tests against fixtures
│   ├── test_validator.py       # NEW — Validation rule tests
│   └── test_pipeline.py        # NEW — End-to-end pipeline tests
```

### Modified Files

```
backend_ml/
├── services/
│   ├── scraper.py              # MODIFIED — Replace Firecrawl with Crawl4AI, make truly async
│   └── llm.py                  # MODIFIED — Extract prompt to file, delegate to extractor.py
├── main.py                     # MODIFIED — Use IngestionPipeline, add structured logging
├── requirements.txt            # MODIFIED — Add crawl4ai, keep firecrawl (dormant)
```

### Deleted Files

None. `llm.py` is preserved but slimmed down (extraction logic moves to `extractor.py`, prompt moves to `prompts/`).

---

## Fixture-Based Testing System

### Design

Each fixture is a pair: a `.md` file containing real scraped Markdown from a pantry website, and a `.json` file containing the hand-verified expected extraction result.

Fixtures cover the diversity of real-world pantry sites:

| Fixture | Description | Key Testing Goal |
|---------|-------------|-----------------|
| `simple_static.md` | Clean static HTML pantry page with clear hours, address, rules | Baseline accuracy — should get confidence 8-10 |
| `wordpress_complex.md` | WordPress site with sidebars, popups, unrelated content mixed in | Noise filtering — can the extractor find the signal? |
| `minimal_info.md` | Page with only a name and vague mention of food | Low confidence handling — should report confidence 2-4 |
| `outdated_info.md` | Page with hours from 2 years ago, "temporarily closed" banner | Staleness detection — should flag CLOSED or low confidence |
| `multilingual.md` | Spanish/English bilingual food pantry page | Multilingual extraction — should extract English fields correctly |

### Expected Output Format

```json
{
  "name": "Example Food Pantry",
  "status": "OPEN",
  "hours_notes": "Mon-Fri 9am-5pm, Sat 10am-2pm",
  "hours_today": "9am-5pm",
  "eligibility_rules": ["Must live in Fulton County", "Photo ID required"],
  "is_id_required": true,
  "residency_req": "Fulton County residents",
  "special_notes": null,
  "confidence": 9,
  "_meta": {
    "source_url": "https://example.org/food-pantry",
    "scraped_date": "2026-02-14",
    "verified_by": "human",
    "notes": "Clear, well-structured page. All fields directly extractable."
  }
}
```

The `_meta` field is for fixture management only — not used in test assertions.

### Test Implementation

**test_extractor.py** — Parametrized fixture tests:

```python
import pytest
import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "scraping"

def get_fixture_pairs():
    pairs = []
    for md_file in sorted(FIXTURES_DIR.glob("*.md")):
        expected_file = FIXTURES_DIR / "expected_outputs" / f"{md_file.stem}.json"
        if expected_file.exists():
            pairs.append(pytest.param(md_file, expected_file, id=md_file.stem))
    return pairs

@pytest.mark.parametrize("md_file,expected_file", get_fixture_pairs())
async def test_extraction_matches_expected(md_file, expected_file):
    markdown = md_file.read_text()
    expected = json.loads(expected_file.read_text())
    result = await extract_pantry_data(markdown)

    # Hard assertions — these must match exactly
    assert result["name"] == expected["name"]
    assert result["status"] == expected["status"]
    if expected["is_id_required"] is not None:
        assert result["is_id_required"] == expected["is_id_required"]

    # Soft assertions — allow tolerance
    assert abs(result["confidence"] - expected["confidence"]) <= 2
    assert 1 <= result["confidence"] <= 10
```

**test_validator.py** — Every business rule:

```python
def test_confidence_below_1_rejected():
    data = valid_pantry_data()
    data["confidence"] = 0
    with pytest.raises(ValidationError):
        validate(data)

def test_confidence_above_10_rejected():
    data = valid_pantry_data()
    data["confidence"] = 11
    with pytest.raises(ValidationError):
        validate(data)

def test_empty_name_rejected():
    data = valid_pantry_data()
    data["name"] = ""
    with pytest.raises(ValidationError):
        validate(data)

def test_invalid_status_rejected():
    data = valid_pantry_data()
    data["status"] = "MAYBE"
    with pytest.raises(ValidationError):
        validate(data)

def test_future_timestamp_rejected():
    data = valid_pantry_data()
    data["last_updated"] = "2030-01-01T00:00:00Z"
    with pytest.raises(ValidationError):
        validate(data)

def test_valid_data_passes():
    data = valid_pantry_data()
    result = validate(data)
    assert result.confidence == 8
```

**test_scraper.py** — Mocked HTTP, no live calls:

```python
async def test_scraper_returns_markdown(mock_crawl4ai):
    mock_crawl4ai.return_value = "# Food Pantry\nOpen Mon-Fri 9am-5pm"
    result = await scraper.scrape_url("https://example.com")
    assert result is not None
    assert "Food Pantry" in result

async def test_scraper_timeout_returns_none(mock_crawl4ai):
    mock_crawl4ai.side_effect = TimeoutError()
    result = await scraper.scrape_url("https://slow-site.com")
    assert result is None

async def test_scraper_empty_content_returns_none(mock_crawl4ai):
    mock_crawl4ai.return_value = ""
    result = await scraper.scrape_url("https://empty-site.com")
    assert result is None
```

**test_pipeline.py** — End-to-end with fixtures, mocked DB:

```python
async def test_pipeline_happy_path(mock_db, sample_fixture):
    result = await pipeline.ingest(url="https://example.com", markdown_override=sample_fixture)
    assert result.confidence >= 1
    assert result.status in ["OPEN", "CLOSED", "WAITLIST", "UNKNOWN"]
    mock_db.update_one.assert_called_once()

async def test_pipeline_validation_failure_does_not_store(mock_db, bad_extraction):
    with pytest.raises(ValidationError):
        await pipeline.ingest(url="https://bad-site.com", markdown_override=bad_extraction)
    mock_db.update_one.assert_not_called()

async def test_pipeline_low_confidence_logs_warning(mock_db, minimal_fixture, caplog):
    result = await pipeline.ingest(url="https://minimal.com", markdown_override=minimal_fixture)
    assert result.confidence <= 4
    assert "low_confidence" in caplog.text
```

---

## Logging Requirements

All logging follows `docs/error_monitoring.md` patterns. Use `logging.getLogger("equitable")` with JSON formatting.

| Event | Level | Structured Fields |
|-------|-------|-------------------|
| Scrape started | INFO | `event`, `url`, `tool` (crawl4ai/firecrawl) |
| Scrape completed | INFO | `event`, `url`, `tool`, `content_length`, `duration_ms` |
| Scrape failed | ERROR | `event`, `url`, `tool`, `error`, `duration_ms` |
| Extraction completed | INFO | `event`, `url`, `confidence`, `status`, `duration_ms` |
| Extraction failed | ERROR | `event`, `url`, `error` |
| Low confidence (<= 4) | WARNING | `event`, `url`, `confidence`, `pantry_name` |
| Validation passed | DEBUG | `event`, `url`, `fields_validated` |
| Validation failed | WARNING | `event`, `url`, `reason`, `raw_data` |
| Pipeline complete | INFO | `event`, `url`, `confidence`, `total_duration_ms` |

Replace all `print()` statements in `scraper.py`, `llm.py`, and `main.py` with structured logger calls.

---

## Prompt Versioning

Move the system prompt from the inline string in `llm.py` to a version-controlled Markdown file:

**`backend_ml/prompts/extraction_system.md`** — The full system prompt (content identical to current `SYSTEM_PROMPT_TEMPLATE`, with `{current_date}` and `{day_of_week}` template variables preserved).

**`backend_ml/prompts/extraction_examples.md`** — Few-shot examples to anchor extraction behavior:

```markdown
## Example 1: Well-structured pantry page

### Input (Markdown excerpt)
> **Hours:** Monday-Friday 9am-5pm, Saturday 10am-2pm
> **Requirements:** Photo ID, proof of address in Fulton County
> **Note:** Closed for Thanksgiving week

### Expected Output
{
  "status": "OPEN",
  "hours_notes": "Mon-Fri 9am-5pm, Sat 10am-2pm",
  "hours_today": "[depends on day]",
  "eligibility_rules": ["Photo ID required", "Proof of address in Fulton County required"],
  "is_id_required": true,
  "residency_req": "Fulton County",
  "special_notes": "Closed for Thanksgiving week",
  "confidence": 9
}

## Example 2: Minimal church page

### Input (Markdown excerpt)
> First Baptist Church welcomes all. We have various ministries including
> a food ministry that serves our community.

### Expected Output
{
  "status": "OPEN",
  "hours_notes": "Not listed on website",
  "hours_today": "Hours not listed",
  "eligibility_rules": ["Open to all - no restrictions listed"],
  "is_id_required": false,
  "residency_req": null,
  "special_notes": null,
  "confidence": 3
}
```

The extractor loads both files at initialization and injects them into the Gemini call.

---

## Sequencing

Build order with explicit handoffs:

### Step 1: Scraping Quality Agent — Foundation (no external dependencies)

1. Create `backend_ml/prompts/extraction_system.md` — move prompt from `llm.py`
2. Create `backend_ml/prompts/extraction_examples.md` — write 3-4 few-shot examples
3. Create `backend_ml/services/validator.py` — implement all validation rules
4. Create `backend_ml/tests/test_validator.py` — test every rule
5. Create fixture files in `backend_ml/tests/fixtures/scraping/` — at least 5 fixtures with expected outputs

### Step 2: Scraping Quality Agent — Scraper Swap

6. Install `crawl4ai` — add to `requirements.txt`
7. Rewrite `backend_ml/services/scraper.py` — replace Firecrawl with Crawl4AI, make truly async
8. Create `backend_ml/tests/test_scraper.py` — mocked HTTP tests

### Step 3: Scraping Quality Agent — Extractor Refactor

9. Create `backend_ml/services/extractor.py` — extract from `llm.py`, load prompts from files
10. Create `backend_ml/tests/test_extractor.py` — parametrized fixture tests
11. Slim down `llm.py` — keep only the Gemini client singleton, delegate extraction logic

### Step 4: Scraping Quality Agent — Pipeline Orchestrator

12. Create `backend_ml/services/ingestion_pipeline.py` — wire scrape → extract → validate
13. Create `backend_ml/tests/test_pipeline.py` — end-to-end fixture tests
14. Add structured logging throughout (replace all `print()`)

### Step 5: Backend Agent — Integration

15. Update `main.py` — use `IngestionPipeline` in the ingest endpoint
16. Verify all smoke tests pass
17. Manual integration test: scrape 3 real Atlanta pantry URLs end-to-end

---

## Testing Requirements

### Backend Test Checklist

- [x] `test_validator.py` — confidence range (1-10), status enum, empty name, future timestamp, valid data passes
- [x] `test_scraper.py` — returns Markdown, handles timeout, handles empty content, handles HTTP errors
- [x] `test_extractor.py` — parametrized against all 5+ fixtures, name match, status match, confidence within ±2
- [x] `test_pipeline.py` — happy path stores to DB, validation failure skips store, low confidence logs warning

### Integration/Smoke Test Checklist

- [x] `POST /pantries/{id}/ingest` still returns valid `Pantry` with all required fields
- [x] `/pantries` still returns valid list
- [x] `/pantries/nearby` still returns geospatially correct results
- [x] Health check returns 200
- [x] Confidence scores are 1-10 and non-null for scraped pantries
- [x] Scraping pipeline produces valid output for test fixture URLs

### Regression Prevention

**Existing tests that must still pass:**
- All current smoke tests listed in `CLAUDE.md`
- The ingest endpoint must return the same response shape (`Pantry` model)

**New tests being added:**
- `test_validator.py` — 6+ tests covering every validation rule
- `test_scraper.py` — 4+ tests covering success, timeout, empty, HTTP error
- `test_extractor.py` — 5+ parametrized tests (one per fixture)
- `test_pipeline.py` — 3+ integration tests

**Manual verification steps:**
- Scrape 3 real Atlanta pantry URLs and verify confidence scores are reasonable
- Compare Crawl4AI Markdown output quality against Firecrawl for the same URLs
- Verify Render deployment works with Crawl4AI (Chromium availability)

---

## Handoffs

- **Scraping Quality Agent needs:** This spec, fixture creation guidelines, access to real pantry URLs for fixture sourcing
- **Backend Agent needs:** Updated `IngestionPipeline` interface to wire into `main.py`, confirmation that the `Pantry` response shape is unchanged
- **Frontend Data Agent needs:** Nothing — no API contract changes
- **Frontend UI Agent needs:** Nothing — no UI changes in this phase

---

## Risks & Open Questions

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Crawl4AI can't run on Render free tier (Chromium too heavy) | Medium | High | Test on Render before committing. Fallback: keep Firecrawl, re-evaluate with Render paid tier ($7/mo) |
| Crawl4AI fails on Cloudflare-protected sites | Medium | Medium | Monitor failure rates during multi-city seeding. If >15%, promote hybrid approach (ADR follow-up) |
| Fixture tests are flaky because Gemini output varies | Medium | Medium | Use tolerance bands (confidence ±2), pin Gemini temperature to 0, test critical fields only |
| Prompt versioning adds file I/O at startup | Low | Low | Load prompts once at service initialization, cache in memory |

### Open Questions

1. **Render + Chromium**: Does Render's free tier Docker image support headless Chromium? Needs a quick spike before Step 2.
2. **Gemini temperature**: Should we set temperature=0 for maximum determinism in fixture tests? Current code uses default temperature.
3. **Fixture sourcing**: Should we scrape real pantry sites now and save the Markdown, or create synthetic fixtures? Recommendation: real sites — synthetic fixtures won't catch real-world edge cases.
