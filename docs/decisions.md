# Architecture Decision Records

This document tracks significant technology and architecture decisions for EquiTable. Each decision follows a structured format so future contributors (including AI agents) understand not just _what_ was chosen, but _why_.

---

## ADR-001: FastAPI over Flask/Django for Backend

**Date**: 2025-01  
**Status**: Accepted

**Context**: Needed a Python web framework for the API layer. The app is API-only (no server-rendered templates), requires async support for MongoDB and external API calls (Gemini, Firecrawl), and benefits from automatic OpenAPI docs.

**Options Considered**:
| Criteria | FastAPI | Flask | Django REST |
|----------|---------|-------|-------------|
| Async native | Yes | No (requires extensions) | Partial (Django 4.1+) |
| Auto API docs | Yes (Swagger + ReDoc) | No (needs flask-restx) | Yes (via DRF) |
| Pydantic integration | Native | No | Serializers (different) |
| Learning curve | Low | Low | Medium-High |
| Ecosystem size | Growing | Mature | Mature |

**Decision**: FastAPI — async-native, Pydantic-first, auto-generates OpenAPI docs, lightweight for an API-only service.

**Consequences**: Must use async libraries everywhere (Motor for MongoDB, httpx for HTTP). Community smaller than Flask/Django but sufficient. Deployment straightforward with Uvicorn.

---

## ADR-002: MongoDB Atlas over PostgreSQL

**Date**: 2025-01  
**Status**: Accepted

**Context**: Pantry data is semi-structured — different pantries have different fields available (some have hours, some don't; some have eligibility rules, some don't). Need geospatial queries for "nearby" search. Need a hosted solution for the free tier.

**Options Considered**:
| Criteria | MongoDB Atlas | PostgreSQL (Supabase) | SQLite |
|----------|---------------|----------------------|--------|
| Semi-structured data | Native (documents) | JSONB (works but awkward) | Limited |
| Geospatial | 2dsphere index, $geoNear | PostGIS (powerful but complex) | None |
| Free hosted tier | Yes (512MB) | Yes (500MB) | N/A (local) |
| Schema flexibility | Schema-less | Schema migrations needed | Schema migrations |
| Async Python driver | Motor | asyncpg | aiosqlite |

**Decision**: MongoDB Atlas — document model fits naturally (pantry data varies per source), 2dsphere indexing is simple for geo queries, free tier is generous, Motor async driver integrates cleanly with FastAPI.

**Consequences**: No enforced schema at DB level — Pydantic models enforce shape at application level. Joins are painful if we need relational queries later (user → saved pantries), but MongoDB references + application-level joins are sufficient for our scale. If we outgrow this, consider adding PostgreSQL alongside for user/relational data.

---

## ADR-003: Gemini 2.0 Flash over GPT-4o / Claude for Extraction

**Date**: 2025-01  
**Status**: Accepted

**Context**: Need an LLM to convert scraped Markdown into structured pantry JSON. Requires reliable JSON output, understanding of schedules/hours, and good instruction following. Must be cost-effective at scale (potentially hundreds of extractions per day with multi-city expansion).

**Options Considered**:
| Criteria | Gemini 2.0 Flash | GPT-4o-mini | Claude 3.5 Haiku |
|----------|-------------------|-------------|------------------|
| Cost per 1M tokens (input) | $0.075 | $0.15 | $0.25 |
| JSON mode | Yes | Yes | Yes (tool use) |
| Speed | Fast | Fast | Fast |
| Instruction following | Good | Good | Good |
| Free tier | Generous (Google AI Studio) | Limited | Limited |

**Decision**: Gemini 2.0 Flash — cheapest option with comparable quality for structured extraction tasks, generous free tier for development, and Google AI Studio makes prompt iteration easy.

**Consequences**: Locked into Google's API. If extraction quality becomes an issue, we can swap to GPT-4o-mini or Claude Haiku without major refactoring since the extractor service is isolated behind `extractor.py`. The extraction prompt is version-controlled in `backend_ml/prompts/` for easy iteration.

**Re-evaluation trigger**: If confidence scores consistently fall below 6/10 average across fixture tests after prompt optimization, evaluate switching models.

---

## ADR-004: Firecrawl for Web Scraping

**Date**: 2025-01
**Status**: Superseded by ADR-008

**Context**: Need to convert pantry websites into clean text/Markdown that the LLM can process. Sites vary wildly — WordPress, Wix, Squarespace, plain HTML, Facebook pages, PDFs.

**Options Considered**:
| Criteria | Firecrawl | Playwright | Crawl4AI | BeautifulSoup |
|----------|-----------|------------|----------|---------------|
| JS rendering | Yes | Yes | Yes | No |
| Output quality | Clean Markdown | Raw HTML (needs processing) | LLM-optimized Markdown | Raw HTML |
| Self-hosted | No (SaaS) | Yes | Yes | Yes |
| Cost | $0.001/page (paid) | Free | Free | Free |
| Setup complexity | Low (API call) | Medium | Medium | Low |
| Cloudflare handling | Good | Good | Partial | Poor |

**Decision**: Firecrawl — fastest path to clean Markdown output, minimal setup, handles JS rendering and most anti-bot measures.

**Consequences**: Ongoing cost per scrape. Dependency on external service. May hit rate limits with multi-city expansion. For Phase 2 (Scraping Quality Overhaul), evaluating a hybrid approach: Firecrawl for complex JS-heavy sites, lighter tools for simple static sites.

**Re-evaluation trigger**: When multi-city expansion requires >1000 scrapes/day or costs exceed $50/month.

---

## ADR-005: Vercel + Render Deployment Split

**Date**: 2025-01  
**Status**: Accepted

**Context**: Need to deploy a React SPA frontend and a Python FastAPI backend. Both should have free tiers for a passion project, support custom domains, and handle the deployment model naturally (static site vs. ASGI server).

**Options Considered**:
| Criteria | Vercel + Render | Railway | Fly.io | AWS (Amplify + Lambda) |
|----------|-----------------|---------|--------|------------------------|
| Frontend hosting | Excellent (Vercel core) | Good | Good | Good (Amplify) |
| Python backend | N/A (Render) | Good | Good | Complex (Lambda) |
| Free tier | Generous (both) | $5 credit/mo | $5 credit/mo | Generous but complex |
| DX | Excellent | Good | Medium | Poor |
| Cold starts | Render free = yes (~30s) | Minimal | Minimal | Lambda = yes |

**Decision**: Vercel for frontend (optimized for React/Vite SPAs, instant deploys, great DX), Render for backend (simple Procfile deployment, free tier with auto-sleep).

**Consequences**: Render free tier has cold starts (~30 seconds after inactivity). Acceptable for a passion project. If latency becomes an issue, upgrade to Render paid ($7/mo) or migrate backend to Railway. CORS configuration needed between Vercel and Render domains.

---

## ADR-006: React 19 + Vite 7 over Next.js

**Date**: 2025-01  
**Status**: Accepted

**Context**: Frontend framework choice. The app is a client-side SPA (no SEO needs for map/app pages), has a separate Python backend (not Node.js), and needs fast development iteration.

**Options Considered**:
| Criteria | React + Vite | Next.js | Remix |
|----------|-------------|---------|-------|
| SPA suitability | Native | Overkill (SSR-first) | Overkill |
| Separate backend | Clean separation | Tempts mixing backend in | Tempts mixing |
| Build speed | Fast (Vite) | Slower (Webpack/Turbopack) | Medium |
| Complexity | Low | Medium-High | Medium |
| Google Maps compat | Good | Good (but hydration issues) | Good |

**Decision**: React 19 + Vite 7 — pure SPA is the right model since we have a separate Python backend, Vite is fastest for dev iteration, and no SSR complexity to deal with.

**Consequences**: No SSR means the landing page won't be SEO-optimized, but that's acceptable — the value is in the map app, not search ranking. If we later need SSR for a public-facing landing page, can add a static site generator or migrate landing page only.

---

## ADR-007: Phase Ordering — Scraping Quality Before Multi-City

**Date**: 2025-02  
**Status**: Accepted

**Context**: Two major features are planned: multi-city expansion (live async scraping for new cities) and scraping quality overhaul (better extraction, validation, confidence calibration). The question is which to build first.

**Decision**: Scraping quality first (Phase 2 before Phase 1 in the roadmap).

**Rationale**: Multi-city expansion multiplies the surface area of scraping. If the pipeline produces unreliable data, scaling it to more cities just produces more unreliable data across more cities. Fixing quality first means:

- Fixture-based tests catch regressions before they ship
- Confidence scores are calibrated and meaningful
- Validation layer catches bad extractions before they reach the DB
- When multi-city launches, data quality is consistent from day one

**Consequences**: Multi-city is delayed. Users only see Atlanta data for longer. Acceptable tradeoff — wrong data is worse than limited data.

---

## ADR-008: Crawl4AI as Primary Scraper (Supersedes ADR-004)

**Date**: 2026-02-14
**Status**: Accepted — superseded in part by ADR-021 (free fallback promoted)

**Context**: ADR-004 marked Firecrawl as "Under Re-evaluation" for Phase 2. With multi-city expansion approaching, we need a scraping solution that is: (a) cost-effective at >1000 scrapes/day, (b) async-native for our FastAPI stack, (c) produces clean Markdown for LLM extraction. The current Firecrawl integration is synchronous (blocking the event loop), costs $0.001/page (scaling to $30+/mo), and is the sole point of failure.

**Options Considered**:
| Criteria | Firecrawl (keep) | Crawl4AI (replace) | Playwright (replace) | Hybrid (Crawl4AI + Firecrawl) |
|----------|-----------------|-------------------|---------------------|-------------------------------|
| Fit | 4 | 4 | 3 | 5 |
| DX | 5 | 3 | 3 | 3 |
| Maturity | 4 | 3 | 5 | 3 |
| Performance | 3 | 4 | 3 | 4 |
| Integration | 3 | 5 | 4 | 4 |
| Cost | 2 | 5 | 5 | 4 |
| **Total** | **21** | **24** | **23** | **23** |

**Decision**: Crawl4AI as the primary (and initially only) scraper. It scores highest overall due to: zero per-page cost, async-native Python API, clean Markdown output purpose-built for LLM pipelines, and active maintenance. Firecrawl remains in `requirements.txt` as a dormant dependency — ready to be promoted to a fallback if Crawl4AI failure rates exceed 15% during multi-city seeding.

The scraper interface (`url → Optional[str]`) is designed so adding a Firecrawl fallback is a one-function change, requiring no pipeline or API modifications.

**Consequences**:

- Crawl4AI requires Chromium on the deployment server. Must verify Render compatibility before merging.
- Firecrawl API key stays configured but is not called at runtime. Monthly cost drops to $0 for scraping.
- ADR-004 status changes to "Superseded by ADR-008".
- **Re-evaluation trigger**: If Crawl4AI fails on >15% of sites during Tier 1 city seeding, implement hybrid fallback to Firecrawl.

---

## ADR-009: Multi-City Expansion — City Filtering and Seed Infrastructure

**Date**: 2026-02-15
**Status**: Accepted

**Context**: EquiTable served only Atlanta with 15 hardcoded pantries. Phase 1 expands to 4 new Tier 1 cities (NYC, LA, Chicago, Houston) with seed data, city-filtered API, and a frontend city selector.

**Decision**:

- Add optional `city`/`state` fields to Pantry and PantryCreate models (not PantryUpdate — LLM doesn't extract city)
- `GET /pantries` gains optional `city`/`state` query params (backward-compatible)
- New `GET /cities` aggregation endpoint returns city list with counts and map centers
- Seed script (`seed_cities.py`) upserts by `source_url` with 24h freshness skip
- Unique sparse index on `source_url` prevents duplicates
- Frontend city selector overlay on MapPage, dynamic map centering, city in URL search params

**Consequences**:

- Old clients that don't pass city/state params get all pantries (backward-compatible)
- Seed data in `data/seed_urls.json` is developer-curated; live discovery is Phase 3+
- `source_url` uniqueness constraint means existing Atlanta data needs city/state backfilled via seed script

---

## ADR-010: Unified Single-Page Architecture

**Date**: 2026-02-16
**Status**: Accepted

**Context**: The two-page split (landing `/` + map `/map`) created a disconnected experience. Users had to click through to see the product. Modern product sites embed interactive demos in the scroll flow.

**Decision**: Merge landing and map into a single scrolling page with a lazy-loaded map preview section and a full-screen map overlay. Keep `/map` as a direct URL that auto-expands the overlay. Use Framer Motion `AnimatePresence` for overlay animations (not `layoutId`, which would cause two map instances to need state sync). Lazy-load Google Maps API via `useInView` with 200px preload margin. Use `gestureHandling="cooperative"` in preview mode so scroll passes through. Respect `prefers-reduced-motion` via a custom hook.

**Consequences**: `LandingPage.jsx` and `MapPage.jsx` are replaced by `UnifiedPage.jsx`. Map components are extracted into reusable `MapExperience.jsx`. Google Maps API is lazy-loaded via IntersectionObserver. Two map instances briefly coexist (preview + overlay) but only one is visible. All existing map functionality is preserved. `/map` bookmarks continue to work.

---

## ADR-011: Google Places Text Search (New) for URL Discovery

**Date**: 2026-02-16
**Status**: Accepted

**Context**: Live Discovery needs to find food pantry/food bank website URLs near a user's search location. The system must return the actual website URL (for scraping via Crawl4AI), plus lat/lng and address. This is a passion project, so cost matters — ideally $0/month at low usage.

**Options Considered**:
| Criteria | Google Places Text Search (New) | Google Custom Search | SerpAPI | Yelp Fusion | Curated seed lists |
|----------|-------------------------------|---------------------|---------|-------------|-------------------|
| Free tier | 1,000/mo (Enterprise) | Closed to new users | 100/mo | None ($7.99/1K) | Unlimited |
| Returns website URL | Yes (`websiteUri`) | Indirectly (search results) | Indirectly | Sometimes | Manual |
| Returns lat/lng | Yes | No | No | Yes | Manual |
| Result quality | Excellent (structured data) | Poor (directories mixed in) | Poor (directories mixed in) | Poor coverage of pantries | High (hand-picked) |
| Requires curation | No | N/A | No | No | Yes (labor-intensive) |

**Decision**: Google Places Text Search (New) with Enterprise field mask (`websiteUri`, `displayName`, `formattedAddress`, `location`, `id`). At our expected usage (~50-100 requests/month, or ~2-3 discovery searches/day), we stay well within the 1,000 free Enterprise requests/month. The API returns structured business data with lat/lng and website URLs in a single call — no separate geocoding or URL extraction needed.

**Consequences**:

- Requires a Google Cloud project with Places API (New) enabled and a `GOOGLE_PLACES_API_KEY` environment variable.
- Food pantries without websites on Google Maps will be stored with basic data (name, address, lat/lng) at `confidence: 3`.
- The 1,000/month free tier is sufficient for organic usage. If we scale to >30 discovery searches/day, cost rises to $35/1,000 requests — revisit pricing at that point.
- Curated seed lists (`data/seed_urls.json`) remain the primary source for Tier 1/2 cities. Places API is for Tier 3 (on-demand) discovery only.

**Re-evaluation trigger**: If Places API free tier terms change, or if >20% of results lack `websiteUri`, evaluate adding SerpAPI as a supplementary source.

---

## ADR-012: Server-Sent Events (SSE) for Discovery Streaming

**Date**: 2026-02-16
**Status**: Accepted

**Context**: Live Discovery scrapes 5-10 pantry URLs per job, taking 30-60 seconds total. Results should stream to the frontend progressively (markers appear one by one) rather than arriving in bulk after completion. Need to choose between polling, SSE, and WebSockets.

**Options Considered**:
| Criteria | SSE | WebSockets | Polling (2s interval) |
|----------|-----|------------|----------------------|
| Complexity | Low | High | Low |
| Real-time feel | Excellent (instant) | Excellent | Poor (2s delay) |
| Server library | `sse-starlette` (mature) | `websockets` + manager | None needed |
| Client API | Native `EventSource` | `WebSocket` + reconnection | `setInterval` + fetch |
| Auto-reconnect | Built-in (browser) | Must implement | N/A |
| Render.com compat | Good | Fragile (cold starts kill WS) | Good |
| Bidirectional | No (server→client only) | Yes | No |
| Proxy/CDN compat | Good (standard HTTP) | Needs upgrade support | Excellent |

**Decision**: SSE via `sse-starlette` on the backend and native `EventSource` on the frontend. SSE is the best fit because: (1) we only need server→client streaming, (2) `EventSource` auto-reconnects on network blips, (3) it works over standard HTTP with no WebSocket upgrade, (4) `sse-starlette` integrates cleanly with FastAPI's `StreamingResponse`, and (5) Render's free tier cold starts don't break SSE connections the way they break WebSockets.

A fallback polling endpoint (`GET /discover/status/{job_id}`) is provided for clients behind corporate proxies that block SSE.

**Consequences**:

- New dependency: `sse-starlette ^2.0` in `requirements.txt`.
- In-memory `asyncio.Queue` per active job for event routing (not persisted — if server restarts mid-job, the stream is lost but stored pantries are kept).
- `EventSource` only supports GET requests, so the initial `POST /discover` is a separate call that returns the SSE stream URL.
- Heartbeat comments every 15 seconds keep the connection alive through proxies.

**Re-evaluation trigger**: If we add features requiring bidirectional communication (e.g., user can refine search mid-discovery), evaluate upgrading to WebSockets.

---

## ADR-014: Multi-Query Places Search with Caching

**Date**: 2026-02-17
**Status**: Accepted

**Context**: Live discovery was triggering correctly but returning "no pantries found" because `PlacesClient` used a single combined query (`"food pantry OR food bank near {query}"`), which missed many results. Places without websites were silently skipped, and repeated searches for the same area hit the API every time.

**Options Considered**:
| Criteria | Single query (status quo) | Multi-query + cache |
|----------|--------------------------|---------------------|
| Coverage | ~5-8 results | ~10-20 results (4 queries deduped) |
| No-website places | Skipped entirely | Stored with confidence=3, `google_places_only` flag |
| Repeat searches | Full API cost every time | 7-day cache via MongoDB TTL index |
| Cost per discovery | ~$0.03 (1 query) | ~$0.13 (4 queries), amortized by cache |
| Place Details fallback | None | Fetches website for places missing it |

**Decision**: Multi-query search with 4 queries ("food bank", "food pantry", "food distribution", "community food"), deduplication by `place_id`, Place Details API fallback for missing websites, 7-day result caching in `discovery_cache` collection, and storage of no-website places with `google_places_only: true` and confidence=3.

**Consequences**:
- `_deduplicate()` now returns a 3-tuple: `(to_scrape, to_store_basic, skipped)`.
- `discovery_cache` collection with TTL index added to `database.py`.
- Places without websites appear on the map with a "Limited info" indicator (confidence=3).
- Cache key uses rounded coordinates (2 decimal places) + radius, so nearby searches hit the same cache entry.
- Cost is ~$0.13 per unique location search, but cache eliminates repeat searches for 7 days.

---

## ADR-015: LangSmith for Agent Observability

**Date**: 2026-06-11
**Status**: Accepted

**Context**: The LangGraph refresh agent needs end-to-end tracing of node executions, state transitions, token counts, and latency. The live API path previously had a Braintrust auto-instrument block in `main.py`, but that code was uncommitted work-in-progress and was discarded before this agent was built — so there is no "switch" from Braintrust; the agent is starting fresh. The live `/pantries/{id}/ingest` endpoint does not use LangChain, so it would require manual instrumentation under any observability system. Instrumenting the live path is explicitly out of scope for this agent build.

**Options Considered**:
| Criteria | LangSmith | Braintrust | Custom logging (structured JSON) |
|----------|-----------|------------|----------------------------------|
| LangGraph auto-tracing | Yes (native integration) | No (requires manual spans) | No |
| Node/edge/state visibility | Yes (built-in) | Manual | Manual |
| Token counts + cost | Auto from usage_metadata | Manual | Manual |
| Free tier | Generous | Yes | N/A |
| Setup effort | Env vars only | SDK + wrappers | Significant |

**Decision**: LangSmith. `agent/config.py` exposes `setup_langsmith()`, which sets `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_PROJECT=equitable-refresh-agent` when a `LANGCHAIN_API_KEY` or `LANGSMITH_API_KEY` is present in the environment. This is a no-op when the keys are absent (safe in dev/CI without secrets). LangGraph automatically traces every node, edge, and state snapshot — zero glue code required.

**Consequences**:

- Requires a LangSmith account with an API key (`LANGCHAIN_API_KEY`) — the free tier is sufficient.
- The live `/pantries/{id}/ingest` endpoint is not instrumented (it does not go through LangChain). Re-instrumenting the live path is a separate concern and can be revisited later.
- Traces are visible in the LangSmith UI under the project `equitable-refresh-agent`, including per-node latency, input/output state, and token usage.

**Re-evaluation trigger**: If the live path grows complex enough to warrant observability, evaluate adding LangSmith manual spans or a lightweight structured-logging alternative to the existing `docs/error_monitoring.md` patterns.

---

## ADR-016: LangGraph for Agent Orchestration

**Date**: 2026-06-11
**Status**: Accepted

**Context**: The refresh agent needs a directed state machine with: a conditional retry/escalation loop inside a per-source extraction flow, fan-out across multiple sources, and a curator stage before the fan-out. The existing live discovery path already does async parallel scraping (`asyncio.Semaphore`, `asyncio.gather`) but has no retry loop, no source prioritization, and no model routing — the live path is demand-driven and latency-sensitive, which makes those additions inappropriate there. The refresh agent is a background batch job where latency is acceptable. A secondary motivation is demonstrating production agent-engineering patterns (state machines, subgraph composition, conditional edges) — deliberate even where a plain async implementation would meet the functional need.

**Options Considered**:
| Criteria | LangGraph | Plain asyncio (extend existing) | CrewAI / AutoGen |
|----------|-----------|----------------------------------|------------------|
| Conditional retry edges | Native (add_conditional_edges) | Manual (while loop) | Framework-specific |
| Subgraph composition/reuse | Native | Custom wiring | Limited |
| Durable checkpointing | Native (pluggable backends) | Not built-in | Not built-in |
| LangSmith auto-tracing | Native | No | Partial |
| Learning signal | High | Low | Medium |
| Overhead | Small (state dicts) | Minimal | High (agent abstractions) |

**Decision**: LangGraph. The parent graph topology is `load_sources → curator → process_sources (fan-out) → aggregate_report → update_metrics`. The per-source extraction is assembled as a **reusable subgraph** (`scrape → extract → validate → [retry loop | persist]`) so it can later be composed into other pipelines (e.g., the live discovery path) without rewriting. The `should_retry` conditional edge feeds validation failures and low-confidence signals back to the extract node with escalated model tier. Installed versions: langgraph 1.2.4, langchain-core 1.4.6, langchain-google-genai 4.2.5.

**Consequences**:

- New dependencies: `langgraph>=1.2`, `langchain-core>=1.4`, `langchain-google-genai>=4.2`, `langsmith>=0.8` added to `requirements.txt`.
- State is typed (`ParentState`, `ExtractionState` as TypedDicts; `ExtractionResult` as a Pydantic model for structured LLM output).
- The live path (`services/discovery_service.py`, `services/ingestion_pipeline.py`) is untouched — the agent is additive, not a rewrite.
- The extraction subgraph is designed so its `scrape → extract → validate` core can be dropped into the live path later without a graph rewrite.

---

## ADR-017: Standalone Scheduled Refresh Job + Curator Multi-Agent Architecture

**Date**: 2026-06-11
**Status**: Accepted

**Context**: Pantry hours and status go stale — `docs/seed_strategy.md` already calls for a freshness policy. Two places could host a refresh capability: (1) the existing live discovery path (`services/discovery_service.py`), or (2) a new standalone background job. The curator agent ranks sources by reliability and staleness history, which only exists for pantries already in the database — brand-new URLs from live discovery have no history to rank on. The live path is latency-sensitive (users wait for SSE results), and adding retry loops, model escalation, and LLM-based curation there would increase latency and complexity without benefit. Deploying a standalone job keeps the live API untouched and preserves its current performance characteristics.

**Decision**: Standalone background refresh job (`backend_ml/agent/`, runnable as `python -m agent.refresh`). The job:

1. `load_sources` — queries pantries with `source_url` present and `last_updated` older than `FRESHNESS_FLOOR_HOURS` (24 h), joining `source_metrics` history.
2. `curator` — quarantines sources with `consecutive_failures > QUARANTINE_THRESHOLD` (5), then ranks the rest by staleness, reliability, and city diversity (LLM ranker using `gemini-2.0-flash-lite`; deterministic staleness fallback on cold start or ranker failure).
3. `process_sources` — async fan-out (semaphore cap `MAX_CONCURRENT=4`) over the curator's selection, each running the extraction subgraph.
4. `aggregate_report` + `update_metrics` — write per-source metrics to the new `source_metrics` collection.

The live path (`/discover`, `/pantries/{id}/ingest`) is not modified. Onboarding brand-new URLs stays with `scripts/seed_cities.py`. Deployment to AWS Fargate + EventBridge is covered separately (ADR-019, deferred to the deployment plan).

**Consequences**:

- New `source_metrics` collection in MongoDB Atlas (unique index on `source_url`) tracks per-source run history (successes, failures, consecutive failures, success rate, avg latency, last model used).
- Quarantined sources (chronic failures) are surfaced in the run report for manual review rather than silently skipped.
- Cold-start behavior (no metrics yet) falls back to pure staleness ordering — the job is immediately useful from the first run.
- The curator's LLM ranker is optional and fails gracefully; the job never crashes due to a ranker error.

---

## ADR-018: Cheap-First Model Escalation and Per-Run Cost Budget

**Date**: 2026-06-11
**Status**: Accepted

**Context**: The refresh agent makes one or more Gemini calls per source. Without cost controls, a run over 25 sources with multiple retries each could spend an unpredictable amount. The existing live extractor always uses `gemini-2.0-flash` (ADR-003); for a background batch job, starting cheaper and escalating only on failure is cost-optimal. A per-run dollar budget provides a hard backstop for runaway spend.

**Options Considered**:
| Criteria | Single model (always Flash) | Cheap-first ladder + budget | Per-source cost limit |
|----------|----------------------------|-----------------------------|-----------------------|
| Cost efficiency | Moderate | High (cheap-first) | Moderate |
| Quality recovery | None | Escalates on failure | None |
| Budget enforcement | None | Yes (soft cap) | Partial |
| Configuration complexity | Low | Low (config constants) | Medium |

**Decision**: Three-rung cheap-first ladder with per-retry escalation, plus a per-run `MAX_COST_USD` budget (default $0.50/run):

| Attempt | Model |
|---------|-------|
| Initial (tier 0) | `gemini-2.0-flash-lite` |
| Retry 1 (tier 1) | `gemini-2.0-flash` |
| Retry 2 (tier 2) | `gemini-2.5-flash` |

Escalation triggers on validation failure **or** `confidence < CONFIDENCE_THRESHOLD` (6), up to `MAX_RETRIES=2` (3 total attempts). The curator uses `gemini-2.0-flash-lite` (ranking is a lightweight task). A `CostTracker` accumulates `tokens × per-model price` (thread-safe) and is checked before admitting each source in the fan-out.

**Important: the per-run budget is a soft cap under concurrency.** Because the budget gate is checked inside the semaphore slot before a source's subgraph runs — and up to `MAX_CONCURRENT` (4) sources can be admitted before any of them have completed and recorded cost — the realized spend can exceed `MAX_COST_USD` by at most `MAX_CONCURRENT × max-per-source-cost` before the remaining queued sources are marked `skipped_budget`. In-flight subgraphs are always allowed to complete. For a batch job expected to cost ~$1–2/month, this overshoot is acceptable; a hard cap would require cost reservation (intentionally not built).

**Consequences**:

- `MODEL_PRICING` constants in `agent/config.py` must be kept current as Google adjusts Gemini pricing — they are the source of truth for all cost accounting.
- Retrying on low confidence (not just hard validation failures) spends tokens on inherently sparse pages that may not improve. The per-run budget is the backstop that prevents runaway spend on these sources.
- Remaining sources that would exceed the budget are skipped (outcome `skipped_budget`) and reported in the run summary; they will be candidates again in the next run.

**Re-evaluation trigger**: If `MODEL_PRICING` drifts more than 20% from actual billing, update the constants. If the soft-cap overshoot ever causes a budget concern, implement cost reservation before the semaphore admit.

---

## ADR-020: MongoDB-Backed LangGraph Checkpointer

**Date**: 2026-06-11
**Status**: Accepted

**Context**: A daily refresh run over 25 sources with up to 3 extraction attempts each takes several minutes. If the process crashes mid-run (OOM, transient network error, container preemption), restarting from scratch wastes tokens and time. LangGraph's checkpointer protocol allows graph state to be persisted after each node completion so that a resumed run picks up where it left off. The agent already uses MongoDB Atlas (ADR-002), making it the natural checkpoint backend — no additional managed service required.

**Options Considered**:
| Criteria | MongoDB (Atlas, existing) | Redis | SQLite (local file) | In-memory (no persistence) |
|----------|--------------------------|-------|---------------------|-----------------------------|
| Durability | Yes (Atlas replication) | Yes | File only | No |
| Resume-on-crash | Yes | Yes | Partial | No |
| Additional service | No (already provisioned) | Yes ($) | No | No |
| LangGraph integration | langgraph-checkpoint-mongodb | langgraph-checkpoint-redis | langgraph-checkpoint-sqlite | Built-in (MemorySaver) |
| Time-travel debugging | Yes (thread_id lookup) | Yes | Yes | No |

**Decision**: `langgraph-checkpoint-mongodb` (version 0.4.0) backed by MongoDB Atlas. `thread_id` is set to the `run_id` (a UUID generated at the start of each run), so each daily run has an isolated checkpoint namespace. Checkpoint collections are written to the same database as the pantries collection.

**Important implementation detail**: `langgraph-checkpoint-mongodb` 0.4.0 ships only a **synchronous** `MongoDBSaver` — there is no `AsyncMongoDBSaver` and no `.aio` submodule. `MongoDBSaver` exposes async-compatible methods (`aget_tuple`, `aput`, `aput_writes`) that delegate to `run_in_executor` internally, so the event loop is not blocked. The `from_conn_string` class method is a synchronous `@contextmanager`. `agent/checkpointer.py` wraps it in an `@asynccontextmanager` — entering the synchronous context manager with a plain `with` block, then yielding the saver to async callers — so the rest of the codebase uses a uniform `async with mongo_checkpointer() as cp:` API.

**Consequences**:

- LangGraph checkpoint collections (`checkpoints`, `checkpoint_writes`, `checkpoint_migrations`) are created automatically in the same Atlas database.
- A resumed run (same `thread_id`) restores state after the last completed node and does not reprocess already-persisted sources. Combined with the freshness floor (24 h), re-runs are naturally idempotent.
- The synchronous-only saver is compatible with LangGraph 1.2.x — if a future `langgraph-checkpoint-mongodb` version ships a true async saver, the `asynccontextmanager` wrapper in `checkpointer.py` can be simplified without changing callers.

**Re-evaluation trigger**: If `langgraph-checkpoint-mongodb` releases an async saver, simplify `checkpointer.py`. If checkpoint storage grows large over time, add a TTL index on the checkpoint collections (checkpoints older than 7 days can be dropped safely).

**Resume-granularity limitation (honest note)**: LangGraph checkpointing operates at superstep/node granularity. Because the entire per-source fan-out is encapsulated inside the single `process_sources` node, a crash mid-fan-out resumes by re-executing that whole node — re-scraping all selected sources for that run. This is **safe**: the per-source upserts are idempotent (keyed on `source_url`) and the 24 h freshness floor means re-refreshed sources are simply no-ops on the next scheduled run. There is no risk of duplicate or clobbered data. However, it is re-work, not per-source incremental resume. True per-source resume would require modeling each source as its own LangGraph branch via the Send API — intentionally deferred because the complexity is not justified for a once-daily batch job at current scale.

---

## ADR-021: Jina Reader as the Free Scraper Fallback (Refines ADR-008)

**Date**: 2026-06-11
**Status**: Accepted

**Context**: Crawl4AI 0.8.9 returns empty markdown on JS/anti-bot pantry sites — verified: 1-character output on two live production sites, even with JS-wait tuning, native and emulated browser modes. The project requires zero scraping cost (ADR-008 premise). Firecrawl (ADR-008's intended fallback) is paid and cannot be the default.

**Decision**: Add a pluggable fallback chain in `ScraperService`. When Crawl4AI yields `< MIN_CONTENT_CHARS` (200 characters), the chain is tried in order. The default chain is `[JinaReaderFetcher]` — Jina Reader (`r.jina.ai`) is free (IP-rate-limited, no signup required), renders JavaScript server-side, and has been verified to recover the failing sites. Firecrawl (ADR-008's intended fallback) is retained as an **opt-in, hard-capped** secondary fetcher that defaults off (`FIRECRAWL_FALLBACK_ENABLED=false`), so the standard deployment configuration costs $0 for scraping. The public `scrape_url(url) -> Optional[str]` interface is fully preserved so the live discovery path requires no changes; a new `scrape_with_provenance(url) -> ScrapeResult` method returns `(content, method)` so the refresh agent can record which tool won. The `scrape_method` field is threaded through agent state (`ExtractionState`) and written to the pantry document by the persist node.

**Consequences**:

- New `services/fallback_fetcher.py` module: `FallbackFetcher` protocol, `JinaReaderFetcher`, `build_default_fallback_chain`, `_bool_env`.
- New `services/firecrawl_fetcher.py` module: `FirecrawlFetcher` with a persistent monthly counter in the `scraper_usage` MongoDB collection — the counter is only written when `FIRECRAWL_FALLBACK_ENABLED=true`, so no new collection is created in the default configuration.
- `firecrawl-py` bumped to `>=4.0` (v2 SDK) in `requirements.txt`.
- `ScrapeResult` dataclass and `MIN_CONTENT_CHARS` constant added to `scraper.py`; `scrape_url` is now a thin backward-compatible wrapper over `scrape_with_provenance`.
- `scrape_method` added to `ExtractionState`; persist node records it on every pantry document write.
- An optional `JINA_API_KEY` raises Jina's rate limit but is never required.

**Re-evaluation trigger**: If Jina rate limits or output quality become inadequate for multi-city seeding volume, reorder the chain (promote capped Firecrawl) or enable a second free reader. If a native async `AsyncMongoDBSaver` lands in `langgraph-checkpoint-mongodb`, revisit whether the `scraper_usage` counter collection should instead be tracked in LangGraph checkpoint state.

---

## ADR-019: Refresh Agent Deployment — ECS Fargate + EventBridge, Public-Subnet (No NAT), SSM Secrets

**Date**: 2026-06-11
**Status**: Accepted

**Context**: The LangGraph refresh agent (ADR-016/017) needs a scheduled, cheap, unattended home. It is a Dockerized CLI (`python -m agent.refresh`) that runs ~once daily, talks to MongoDB Atlas, Gemini, Jina, and LangSmith over the internet, and makes no inbound requests.

**Decision**: Run it on **AWS ECS Fargate** (2 vCPU / 4 GB, x86_64), triggered **once daily by EventBridge Scheduler** (`cron(0 8 * * ? *)` UTC). The task runs in a **public subnet with a public IP and NO NAT Gateway** — a NAT would cost ~$32/mo, dwarfing the ~$1–2/mo job. Secrets (`MONGO_URI`, `GEMINI_API_KEY`, `LANGCHAIN_API_KEY`, `JINA_API_KEY`) live in **SSM Parameter Store SecureStrings** (free) and are injected via the task definition's `secrets`. Atlas network access is opened to **`0.0.0.0/0`** because the Fargate public IP is dynamic and cannot be allow-listed without reintroducing a NAT; security rests on a strong DB password + TLS. Region `us-east-1` (same as the Atlas cluster). Infra was created via raw AWS CLI; policy/task-def files are committed under `deploy/`, and `docs/deploy-refresh-agent.md` is the operating runbook.

**Options Considered**:
| Criteria | Fargate + EventBridge (public subnet) | Fargate (private subnet + NAT) | Lambda | GitHub Actions cron |
|----------|--------------------------------------|-------------------------------|--------|---------------------|
| Cost/mo | ~$1–2 | ~$34 (NAT) | low but 15-min limit + Chromium pain | $0 but shared runners, secrets in GH |
| Chromium/Playwright | Fits in image | Fits | Hard (layers/size) | Fits |
| Scheduling | Native (EventBridge) | Native | Native | Native (cron) |
| Secrets | SSM (free) | SSM | SSM | GH secrets |
| Egress to Atlas/Gemini | Public IP, no NAT | via NAT | via NAT/VPC | runner egress |

**Consequences**:
- DB is reachable from any IP (mitigated by credentials + TLS). Revisit with Atlas PrivateLink (M10+) if the posture needs tightening.
- Image must be built `linux/amd64` (Fargate x86). Pushing a new `:latest` to ECR is the deploy step; scheduled runs pick it up automatically.
- Verified end-to-end on `2026-06-14`: a Fargate run refreshed real Atlas pantries (Gemini-3 extraction, source_metrics written, LangSmith trace captured), exit 0.
- **Re-evaluation trigger**: if daily runs exceed budget, or the security posture must tighten, add NAT+Elastic-IP (allow-listed) or Atlas PrivateLink.

---

## ADR-022: Kubernetes for the API and Refresh Agent (Supersedes ADR-019's deployment topology)

**Date**: 2026-09-05
**Status**: Accepted

**Context**: The refresh agent runs on ECS Fargate triggered by EventBridge Scheduler (ADR-019); the API runs on Render; the frontend on Vercel (ADR-005). Three deployment substrates, each configured by hand through a console or raw CLI calls, with no single artifact describing the system. Adding an environment means repeating console clicks and hoping the second one matches the first.

The forcing function is external and worth stating plainly rather than dressing up: **the target roles (Tesla Infra, Verkada, and most platform positions) screen for Kubernetes and Terraform, and the résumé already claims Kubernetes.** This ADR exists partly to make an existing written claim true. That is a legitimate reason to build something, but it is not a technical justification, so the technical case is made separately below and is expected to stand on its own.

**Options Considered**:

| Criteria | Kubernetes (kind local) | Stay on ECS + Render | Nomad | Plain VM + systemd timers |
|---|---|---|---|---|
| Scheduled job primitive | CronJob, with overlap policy + deadlines | EventBridge + ECS RunTask | Periodic job | systemd timer |
| Overlap protection | Declarative (`concurrencyPolicy: Forbid`) | **None** — EventBridge fires regardless | Declarative | Manual flock |
| API rollout safety | Rolling update, probe-gated, automatic rollback | Render's own, opaque | Rolling | Manual |
| Autoscaling | HPA on real pod metrics | Render plan tiers | Yes | No |
| One artifact describing the system | Yes (`k8s/`) | No — split across 2 consoles | Yes | Partly |
| Local reproduction of prod topology | Yes (kind) | No | Yes | No |
| Operational cost | Real; a control plane to understand | Low | Real | Lowest |
| Job-market value | High | Low | Low | None |

**Decision**: Move the **API service** and the **refresh agent** onto Kubernetes, defined in `k8s/` and running on a local **kind** cluster. The frontend stays on Vercel — it is a static SPA on a CDN, and putting it in a cluster would be strictly worse (no CDN edge, more to operate, zero benefit). ECS is left intact and working during the migration rather than torn down; the image still builds `--target agent` with the same CMD, so `deploy/task-definition.json` needs no edits and the ECS path remains a live rollback.

**The technical case, independent of the job market**: three real things improve.

1. **Overlap protection becomes declarative.** EventBridge fires on schedule with no knowledge of whether the previous task is still running. Two concurrent crawls would double Gemini spend against a budget enforced per-process, and race on the same pantry documents. Today nothing prevents this; it has not happened because runs finish in minutes and fire fortnightly. `concurrencyPolicy: Forbid` makes it structurally impossible instead of merely unlikely.
2. **The API gains probe-gated rollouts.** Render decides when a deploy is healthy. Here, readiness is defined against a real dependency check (ADR-025), and `maxUnavailable: 0` means a broken image never displaces a working one.
3. **One reviewable artifact.** The system is a directory of YAML instead of two consoles and a runbook, which is also the precondition for Terraform (ADR-029).

**Consequences**:

- A control plane to operate and understand — genuinely more complex than `aws ecs run-task`. For a fortnightly batch job and a low-traffic API, **this is more machinery than the workload requires**, and that should be said out loud rather than rationalized away.
- Local kind keeps the marginal cost at **$0/month**, preserving the existing ceiling. Note this project was never $0 overall: ADR-019 records ≈$1–2/mo ECS + ≈$0.50–1/mo Gemini. The $0 claim is about *scraping* (ADR-021), not the whole system.
- kind is not production. A cluster running on one laptop with no real traffic proves the manifests are correct and the workloads run; it proves nothing about behavior under load, node failure, or a real upgrade. The README's "What this does not prove" section records exactly what is and is not demonstrated.
- Two images now come from one Dockerfile via `--target`, sharing the Chromium layer.

**Re-evaluation trigger**: If the API ever needs real uptime for actual users, move to a managed control plane (EKS/GKE) and price it before committing — a managed control plane is ~$72/mo before any nodes, which breaks the cost posture entirely. If the Kubernetes machinery is never exercised beyond the initial migration, the honest move is to acknowledge ECS was sufficient.

---

## ADR-023: CronJob for the Scheduled Refresh, and Why the Schedule Changed Shape

**Date**: 2026-09-05
**Status**: Accepted

**Context**: The refresh agent is a batch process (`python -m agent.refresh`) that exits when done. It ran under EventBridge Scheduler at `rate(14 days)`. Kubernetes offers several ways to run something periodically, and the choice determines what happens on overlap, failure, and hang.

**Options Considered**:

| Criteria | CronJob | Deployment with an internal sleep loop | Argo Workflows / Airflow | Keep EventBridge → in-cluster webhook |
|---|---|---|---|---|
| Native to Kubernetes | Yes | Yes, but misuses the primitive | No (extra system) | No |
| Overlap protection | `concurrencyPolicy: Forbid` | Hand-rolled | Yes | None |
| Hang protection | `activeDeadlineSeconds` | Hand-rolled | Yes | None |
| Retry semantics | `backoffLimit` | Hand-rolled | Yes | EventBridge retry |
| Idle cost | Zero pods between runs | A pod idling 24/7 for a fortnightly job | Control plane always on | Zero |
| Operational surface | Already present | Already present | A whole new system | Cross-cloud coupling |

**Decision**: A **CronJob**. `concurrencyPolicy: Forbid`, `backoffLimit: 2`, `activeDeadlineSeconds: 3600`, `restartPolicy: Never`, `startingDeadlineSeconds: 3600`, `ttlSecondsAfterFinished: 86400`.

A long-running Deployment that sleeps between runs was rejected outright: it burns a pod's resources continuously for a job that runs 26 times a year, and it reimplements — badly — the overlap, retry, and deadline handling the CronJob controller already provides.

**The schedule is not a literal translation, and that is deliberate.** EventBridge `rate(14 days)` is *relative*: it measures from the previous run and drifts across the calendar. Cron is *absolute*: it matches calendar fields and cannot express "every 14 days" at all. The chosen `0 8 1,15 * *` (08:00 UTC on the 1st and 15th) keeps the same ~2-week cadence but pins it to dates, producing 14/15/16-day gaps instead of exactly 14. This changes nothing operationally: `REFRESH_FRESHNESS_HOURS=24` means only pantries staler than a day are candidates, so a gap varying by two days has no effect on what gets refreshed.

**`restartPolicy: Never` over `OnFailure`** is a real choice. `OnFailure` restarts the container inside the same pod, overwriting the previous attempt's logs and hiding attempt count. `Never` creates a fresh pod per attempt: each attempt's logs stay independently inspectable, and — critically — the replacement pod still carries the same `batch.kubernetes.io/job-name` label, which is the anchor that makes resume work (ADR-024).

**Consequences**:

- **A skipped run is dropped, not queued.** `Forbid` does not defer the firing; that slot is simply lost and the next is a fortnight away. Acceptable because the job is idempotent (upserts keyed on `source_url`) and the freshness floor means a missed run only means slightly staler data. If the cadence were hourly this would be the wrong policy.
- `activeDeadlineSeconds` counts from **Job** start across all retries, not per pod. A run that burns its hour on attempt 1 gets no attempt 2. For a job whose observed ECS runtime is minutes against a 60-minute ceiling, that margin is wide, but it is a real interaction and not the "one hour per try" it looks like.
- Cost of a manual run is one command: `kubectl create job --from=cronjob/equitable-refresh`.

**Re-evaluation trigger**: If refresh runs start approaching the hour, re-measure before raising `activeDeadlineSeconds` — a run that slow probably indicates a wedged scrape, which is exactly what the deadline exists to catch. If the cadence ever tightens to daily or hourly, revisit `Forbid` vs `Replace`.

---

## ADR-024: A Stable thread_id — Making Resume-on-Crash Actually Work (Refines ADR-020)

**Date**: 2026-09-05
**Status**: Accepted

**Context**: ADR-020 adopted `langgraph-checkpoint-mongodb` so an interrupted run could resume rather than redo work, and stated: "`thread_id` is set to the `run_id` (a UUID generated at the start of each run), so each daily run has an isolated checkpoint namespace."

Preparing the Kubernetes migration surfaced that **this design silently prevented resume from ever happening.** `agent/cli.py` generated `run_id = str(uuid.uuid4())` at process start and used it as the `thread_id`. A restarted process therefore always produced a *new* UUID, opened a *brand-new* checkpoint namespace, and re-entered the graph at START. Checkpoints were written faithfully on every run and never once read back.

The existing tests did not catch this because they were testing a different thing. `tests/agent/test_checkpointer.py` hardcodes `thread_id = "resume-test-001"` and proves the MongoDB saver is durable across connections — which is true and worth testing. Durability is necessary for resume but not sufficient: nothing tested the entrypoint's choice of thread_id, which is where the behavior actually lived.

This matters beyond tidiness: resume-on-crash was claimed in writing, and the claim was false in production while being defensible in the test suite.

**Options Considered**:

| Criteria | Job name via downward API | Pod name | Hash of the schedule slot | Fixed constant | Random UUID (status quo) |
|---|---|---|---|---|---|
| Stable across pod restarts in a run | **Yes** | No — new pod, new name | Yes | Yes | **No** |
| Distinct between scheduled runs | **Yes** | Yes | Yes | **No** — all runs collide | Yes |
| Works outside Kubernetes | Falls back | Falls back | Needs a clock convention | Yes | Yes |
| Resume actually occurs | **Yes** | No | Yes | Yes, wrongly | **No** |

**Decision**: Resolve the thread_id from a `REFRESH_RUN_ID` environment variable, injected in the CronJob from the pod label `batch.kubernetes.io/job-name` via the downward API. Fall back to `uuid4()` when unset.

The Job name is the correct anchor because it is *both* stable and unique on exactly the right boundaries: every pod belonging to one Job — including `backoffLimit` retries after a crash — sees the same value, while the CronJob controller suffixes each firing with its scheduled timestamp so distinct runs never share a thread. Pod name fails the first property; a fixed constant fails the second and would collapse every run in history onto one thread.

The UUID fallback is not a compromise but the right behavior off-cluster: an ad-hoc local run or the legacy ECS task has no external identity to anchor to, and each such run *should* stand alone. A blank or whitespace-only value falls back too — an empty string is falsy but a perfectly valid dict key, so passing it through would quietly collapse every run onto one shared thread.

`invoke_or_resume()` checks `aget_state(config)` before invoking: a populated snapshot means resume (`ainvoke(None, config)`), an empty one means a fresh start (`ainvoke(initial_state, config)`). Passing the initial state to an existing thread would reset it to START — the original bug, in a new place.

**Consequences**:

- Resume is now verified by behavior, not by proxy. `tests/agent/test_resume.py` crashes a run inside `update_metrics`, restarts on the same thread through a fresh connection, and asserts `load_sources` executed **once** across both runs. Reverting `invoke_or_resume` to always-start-fresh makes that count 2 and the test fails — the regression is genuinely caught, which was confirmed by mutation rather than assumed.
- Re-invoking a **completed** thread returns its final state without redoing work, so a duplicate pod is harmless instead of double-scraping.
- **The resume-granularity limit from ADR-020 still stands and is unchanged by this.** The per-source fan-out lives inside the single `process_sources` node, so a crash mid-fan-out resumes by re-executing that whole node and re-scraping every selected source for that run. What this ADR fixes is narrower but more fundamental: previously the run resumed *nothing at all*. Now it resumes at node granularity. True per-source resume still requires modeling each source as its own branch via the Send API, still deferred.
- ADR-020's sentence about a per-run UUID thread_id is superseded on Kubernetes; it remains accurate for the ECS path.

**Re-evaluation trigger**: If re-scraping a whole batch on a mid-fan-out crash becomes expensive — more sources per run, or a pricier model tier — implement per-source Send-API branches so resume granularity matches the unit of work.

---

## ADR-025: Real Health Probes, and the Liveness/Readiness Split

**Date**: 2026-09-05
**Status**: Accepted

**Context**: Before this, the only health-shaped endpoint was `GET /` returning a hardcoded `{"message": "EquiTable API is running"}`. It reports that the Python process can serialize a dict. It returns 200 while MongoDB is unreachable, while every index is missing, and while every real endpoint returns 500. `tests/test_smoke.py::test_health_check` asserted exactly that behavior.

A load balancer pointed at that endpoint routes traffic to a pod that cannot serve any of it. **That is worse than having no health check**, because it converts "obviously down" into "up and silently failing" — the operator sees green while users see 500s.

**Options Considered**:

| Criteria | Split live/ready | One `/health` checking Mongo for both | One `/health` checking nothing | Deep check (Mongo + Gemini + Jina) |
|---|---|---|---|---|
| Mongo outage → pod killed? | No | **Yes — restart storm** | No | Yes |
| Mongo outage → traffic stops? | Yes | Yes | **No** | Yes |
| Recovers without restart | Yes | No | N/A | No |
| Third-party outage → self-inflicted outage | No | No | No | **Yes** |
| Probe latency bounded | Yes | Yes | Yes | No |

**Decision**: Two endpoints answering two genuinely different questions.

`GET /healthz/live` — **"is this process wedged?"** Dependency-free by design. A liveness failure gets the pod **killed**. If Atlas is unreachable, restarting cannot fix it: the second pod fails identically, so a Mongo-checking liveness probe converts a recoverable dependency blip into a cluster-wide CrashLoopBackOff, and throws away warm connection pools that would have recovered on their own. Liveness must only detect failures that a restart actually repairs — a deadlocked event loop, a wedged process.

`GET /healthz/ready` — **"can this pod serve a request right now?"** Pings MongoDB and returns **503 with the failure reason** when it cannot. A readiness failure only removes the pod from the Service endpoints; the pod keeps running and rejoins automatically when the ping succeeds. This is level-triggered on current state, not latched, which is why a Mongo blip needs no restart.

The ping is bounded by `READINESS_PING_TIMEOUT_SECONDS = 2.0`. **The timeout is as important as the check**: a probe that hangs never reports unready, so kubelet keeps the pod in rotation while it cannot serve — the exact failure the probe exists to prevent. Bounding the wait converts a hang into a definite failure.

A `startupProbe` gates both. The app's lifespan connects to Atlas and ensures five indexes before uvicorn serves anything; on a cold start that takes real time. Without the gate, liveness starts counting immediately and kills the pod mid-startup, forever — a CrashLoopBackOff that reads like a code bug and is actually a probe misconfiguration.

Deliberately **not** checked in readiness: Gemini, Jina, LangSmith. They are used by request-scoped paths, not by the service's ability to answer `/pantries`. Probing them would let a third-party outage take the API out of rotation — importing someone else's downtime as your own.

**Consequences**:

- `readinessProbe.timeoutSeconds` (3s) must stay **greater than** the app's own ping budget (2s). If kubelet gave up first, every slow-but-recoverable ping would read as a hard failure and the app's own 503-with-a-reason would never be seen. The two numbers are coupled; changing one requires changing the other.
- `GET /` is intentionally unchanged — the smoke tests and Render's default check depend on it, and it stays as the concrete example of the naive check these probes replace.
- Seven tests in `tests/test_health_probes.py` cover the cases that matter, which are the negative ones: liveness stays 200 while Mongo is down (the anti-restart-storm property), readiness 503s on a missing handle, on a refused connection, and on a hang past the timeout, then returns to 200 once Mongo recovers.

**Re-evaluation trigger**: If readiness flaps under normal Atlas latency, raise the ping budget and kubelet timeout together rather than removing the check. If the API gains a dependency it genuinely cannot serve without, add it to readiness — never to liveness.

---

## ADR-026: Resource Requests, Limits, and HPA Targets

**Date**: 2026-09-05
**Status**: Accepted

**Context**: Kubernetes needs `requests` (what the scheduler reserves, and what the HPA measures against) and `limits` (the ceiling). Getting these wrong is quiet: too-low memory limits OOM-kill under load, too-low CPU limits throttle into latency, and too-high requests waste capacity and suppress scaling.

There is no production traffic profile for this service. Any number here is an estimate, and pretending otherwise would be the actual mistake.

**Decision and derivation**:

| Workload | CPU req | CPU limit | Mem req | Mem limit |
|---|---|---|---|---|
| API | 200m | 1000m | 512Mi | 2Gi |
| Refresh agent | 500m | 2 | 1Gi | 4Gi |

*Refresh agent* — anchored to something real: the ECS task definition running this exact code at 2 vCPU / 4 GiB, which has run successfully in production since 2026-06-14. Limits match that; requests sit well below because the job is bursty (Chromium spikes during a scrape, idles between sources) and a briefly throttled batch job just takes marginally longer, which costs nothing on a fortnightly schedule.

*API* — CPU request is low because the hot path is Mongo-backed reads, which are I/O-bound; CPU sits near idle. Memory limit is generous because `/pantries/discover` spawns Chromium in-process via Crawl4AI, and **memory limits are enforced by OOM-kill, not throttling** — too low and a user-triggered crawl kills the pod mid-request. 2 GiB is half the ECS figure, on the reasoning that the API crawls one page at a time rather than fanning out.

*HPA*: CPU utilization 70%, min 2, max 6. `averageUtilization` is a percentage of the **request** (200m), so 70% means 140m per pod — anchoring to the request is what keeps the number meaningful. Scale-up stabilizes over 60s so one noisy scrape does not trigger a scale event; scale-down over 300s with one pod per 120s, because discovery responses are long-lived SSE streams and yanking a pod mid-stream drops a user's in-flight results.

**First real measurement** (2026-09-06, idle, on the kind cluster):

| Pod | CPU | Memory | vs. request |
|---|---|---|---|
| equitable-api (×2) | 7–8m | ~112 MiB | 4% of the 200m CPU request, 22% of the 512Mi memory request |

The API idles at roughly a twenty-fifth of its CPU request and a fifth of its memory request. Requests are a floor for the *scheduler* rather than a prediction of idle, and the memory headroom exists for the Chromium spike on `/pantries/discover` that this measurement does not exercise. The honest read: **the memory request is defensible; the CPU request is probably 2–4x too high.** That also means the HPA's 70%-of-200m target (140m/pod) sits even further above real usage than it appears — reinforcing the next bullet.

**Honest limitations** — these belong on the record rather than in a footnote:

- **These numbers are not measured under load.** The table above is idle on a laptop. The values are otherwise anchored to a known-good ECS configuration and to the shape of the workload, then given headroom. The correct process is to run representative traffic, observe actual usage, and set requests near the p50 with limits near the p99. That has not been done, because there is no representative traffic — one idle data point is a start, not a profile.
- **CPU-only HPA is the wrong signal for this service.** The API is I/O-bound; under a burst of discovery requests it will saturate on concurrent scrapes and Mongo round-trips long before CPU reaches 140m per pod. The HPA will sit idle while latency climbs. The right metric is in-flight requests or p99 latency, which needs a custom-metrics adapter. CPU is what `autoscaling/v2` gives without extra infrastructure, and it is what was built. This is a known weakness, not an oversight.
- One uvicorn worker per container is deliberate: multiple in-pod workers hide load from the HPA's per-pod CPU metric and multiply the Mongo connection pool per pod. Scale with replicas, not processes.

**Re-evaluation trigger**: First real traffic. Replace these with observed p50/p99 values, and replace the CPU-based HPA with a latency- or concurrency-based one before claiming the autoscaling is meaningful.

---

## ADR-027: kind with Calico — a NetworkPolicy That Is Actually Enforced

**Date**: 2026-09-05
**Status**: Accepted

**Context**: Phase 1 calls for a NetworkPolicy restricting pod-to-pod traffic. Kubernetes accepts NetworkPolicy objects unconditionally; **enforcement is the CNI plugin's job**. kind's default CNI, kindnet, does not implement NetworkPolicy. It accepts the objects, `kubectl get networkpolicy` lists them, and no packet is ever filtered.

That failure mode is the dangerous kind: a policy that appears applied, reviews as applied, and enforces nothing. Shipping it and describing the workloads as network-isolated would be a false claim backed by convincing-looking evidence.

**Options Considered**:

| Criteria | kind + Calico | kind + kindnet | k3d (Flannel default) | Skip NetworkPolicy |
|---|---|---|---|---|
| Policies enforced | **Yes** | **No — silently inert** | No (Flannel); yes if swapped | N/A |
| Setup complexity | One manifest + `disableDefaultCNI` | None | Similar swap needed | None |
| Claim is truthful | Yes | **No** | No by default | Yes, trivially |

**Decision**: Create the kind cluster with `disableDefaultCNI: true` and `podSubnet: 192.168.0.0/16`, then install Calico. The policy set is deny-all by default, plus three narrow allows: DNS to kube-dns, external egress on 80/443/27017, and ingress to API pods from the `ingress-nginx` namespace only.

Two details are load-bearing:

- **NetworkPolicies are additive and default-allow until a policy selects a pod.** Without the `default-deny-all` baseline that selects everything, the three "allow" policies would grant nothing extra — the traffic was already permitted. The baseline is what makes the allows meaningful.
- **External egress excludes RFC1918 and link-local ranges.** The refresh agent fetches attacker-influenced third-party URLs, so SSRF via a malicious redirect is a real path, and `169.254.169.254` (cloud metadata) sits inside `169.254.0.0/16`. Allowing `0.0.0.0/0` without the exclusions would let a redirect reach cluster-internal services and metadata endpoints.

The API and the refresh agent share a database but never a network path; nothing in the policy set permits traffic between them.

**Consequences**:

- `disableDefaultCNI` means nodes stay `NotReady` until Calico is installed. `scripts/k8s-up.sh` installs it and waits, but a manual `kind create cluster` with this config appears broken until that step runs. Worth knowing before debugging a "broken" cluster.
- DNS is the most confusing thing to get wrong here: with egress denied, a `mongodb+srv://` URI fails at SRV resolution and surfaces as an opaque Mongo timeout rather than "DNS blocked". The dedicated `allow-dns-egress` policy exists to prevent that debugging trap.
- Calico is more machinery than kindnet, and a component that can itself fail.

**Re-evaluation trigger**: If Calico proves unstable on this host, the honest fallback is kindnet **plus** deleting the NetworkPolicy manifests and saying the workloads are not network-isolated — not keeping inert policies that imply otherwise.

---

## ADR-028: Secrets from .env at Apply Time; Self-Signed TLS Locally

**Date**: 2026-09-05
**Status**: Accepted

**Context**: Five credentials are needed (`MONGO_URI`, `GEMINI_API_KEY`, `LANGCHAIN_API_KEY`, `JINA_API_KEY`, `GOOGLE_PLACES_API_KEY`). On ECS they live in SSM Parameter Store SecureStrings (ADR-019). Kubernetes needs them as a Secret, and the hard constraint is that **no real credential may ever enter git** — a secret committed once lives in history forever, and rewriting history is not a remediation anyone reliably completes.

**Decision**: The real Secret is **never a file in the repo**. It is created at apply time from the already-gitignored `backend_ml/.env`:

```
kubectl create secret generic equitable-secrets \
  --namespace equitable --from-env-file=backend_ml/.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

`k8s/11-secret.example.yaml` is committed as a placeholder template with `REPLACE_ME` values, documenting the required keys and the injection path. `scripts/k8s-up.sh` deliberately excludes it from the apply loop — applying it would overwrite the real Secret with placeholders.

`--from-env-file` is preferred over repeated `--from-literal` because the latter puts every credential in shell history in plaintext.

**Ingress TLS**: a self-signed certificate for `equitable.localtest.me`, generated by `scripts/k8s-tls-secret.sh` into the secret name the Ingress already references. `localtest.me` resolves to `127.0.0.1` from any resolver, which matters because TLS certificates cannot be issued for a bare IP — it gives local HTTPS a real hostname with no `/etc/hosts` editing. The generation uses `-addext subjectAltName`: browsers and Go's TLS stack stopped honoring the CN field for hostname verification years ago, so a CN-only cert fails verification while looking correct. On a real cluster, cert-manager issues a trusted certificate into the same secret name and no manifest changes at all.

**Consequences**:

- **A Kubernetes Secret is base64, not encryption.** At rest in etcd it is plaintext unless the cluster enables encryption-at-rest, and anyone with `get secrets` in the namespace can read every value. For a local kind cluster this is acceptable and should not be described as more than it is.
- For a shared or production cluster this is **not** sufficient. The path forward is External Secrets Operator reading the existing SSM parameters (reusing ADR-019's store, which already works), or SOPS-encrypted manifests. Deferred deliberately: it adds a component with no benefit on a single-user local cluster.
- Verified before writing this: no `.env` file is tracked, and `git log --all -- '*.env'` is empty. Only `backend_ml/.env.example` is committed, containing placeholders.
- Self-signed means `curl -k` and a browser warning locally. Expected, and not a defect to work around.

**Re-evaluation trigger**: The moment this runs anywhere another person can reach — move to External Secrets against SSM and enable etcd encryption-at-rest before that, not after.

---

## ADR-029: Terraform Scope — Namespace and Atlas, Not the Cluster or the Workloads

**Date**: 2026-09-06
**Status**: Accepted

**Context**: Infrastructure was created by console clicks and raw CLI calls (ADR-019 records the AWS side explicitly: "Infra was created via raw AWS CLI"). Nothing describes the system as a reviewable artifact, so an infrastructure change gets no review while a one-line code change gets a PR. Terraform is also a standing gap for the target roles.

The real question is not "should we use Terraform" but **what should it own**. Putting everything under Terraform is the obvious answer and the wrong one here.

**Options Considered**:

| Criteria | Namespace + Atlas (chosen) | Everything, incl. cluster + workloads | Cluster only | Nothing (status quo) |
|---|---|---|---|---|
| Single source of truth per object | Yes | Yes | Yes | No |
| `terraform plan` works without a live cluster | **Yes** | **No** — `kubernetes_manifest` needs one at plan time | Yes | N/A |
| Workload changes reviewable as k8s YAML | Yes | No — HCL transliteration | Yes | Yes |
| Duplicates `k8s-up.sh` | No | Yes (cluster) | Yes (cluster) | No |
| Secrets kept out of state | Yes | Only with care | Yes | Yes |

**Decision**: Terraform owns the **Kubernetes namespace, ServiceAccounts, and ConfigMap**, plus **MongoDB Atlas** network access and cluster. It does not own the kind cluster, the workload manifests, or the Secret.

The spec allowed "cluster **or** namespace"; namespace is the better half of that choice because `scripts/k8s-up.sh` already creates the cluster, and a Terraform-managed kind cluster would be a second way to create the same object that can disagree with the first.

Three exclusions, each for a concrete reason:

- **Workload manifests stay YAML.** `kubernetes_manifest` requires a *reachable cluster at plan time*. Adopting it would make the `terraform plan` CI job depend on a live cluster — which defeats the entire purpose of gating changes on a plan. Deployment/Service/Ingress/HPA/CronJob also simply read better as Kubernetes YAML than as HCL restating the same fields.
- **The Secret is owned by neither.** Terraform state stores values in **plaintext**. A `kubernetes_secret` resource would write every API key into the state file and, once the S3 backend is enabled, into a bucket — strictly worse than the status quo. It is created from `.env` at apply time (ADR-028).
- **The kind cluster stays in the script**, per above.

**Atlas is import-guarded and off by default.** `var.manage_atlas` defaults to `false`. The project and cluster already exist and hold production data; applying without matching state makes Terraform plan to *create* a cluster it thinks is missing, and reconciling that against a live database is how databases get destroyed. The documented sequence is `terraform import` → `terraform plan` → confirm "No changes" → only then apply. `prevent_destroy = true` is a backstop, not the plan. `var.atlas_instance_size` is validated against M0/M2/M5 so that moving off the free tier (M2 ≈ $9/mo) is an explicit reviewable change rather than an unnoticed edit.

**Remote state is written but commented out.** Local state keeps `terraform plan` working offline and creates no billable AWS resources for anyone who clones the repo. This is honest about the tradeoff: local state is fine for one operator on one laptop and **not** fine the moment a second person or a CI job can apply, because concurrent applies against unlocked state corrupt it. Locking uses S3 native conditional writes (`use_lockfile`, Terraform ≥ 1.11) rather than the older DynamoDB lock table — one less resource to create, pay for, and forget.

**Consequences**:

- The provider pins `config_context = "kind-equitable"` instead of following the current kubectl context. An apply landing on an unintended cluster is the most expensive available mistake, and defaulting to "whatever is current" invites exactly that.
- Two tools now touch the same namespace: Terraform creates it, kubectl fills it. The boundary is documented in `terraform/README.md` and holds as long as nobody adds workload resources to HCL.
- **`terraform apply` has not been run against Atlas.** `terraform init` and `terraform validate` pass and the config is formatted, but the Atlas resources are unexercised — they need the import and API credentials first. The Kubernetes half is the tested path. Saying the infrastructure "is in Terraform" without that qualifier would overstate it.

**Re-evaluation trigger**: Before a second person can apply, enable the S3 backend — unlocked shared state is a corruption waiting to happen. If Atlas is ever recreated from scratch, do it through Terraform so the import dance is never needed again.

---

## ADR-030: Scraper Metrics — Pull for the API, Pushgateway for the CronJob

**Date**: 2026-09-19
**Status**: Accepted

**Context**: The résumé carried a placeholder for "what fraction of pages Crawl4AI handles vs. the Jina fallback". The only existing evidence was `pantries.scrape_method`, which a read-only aggregation put at **95 Crawl4AI / 33 Jina / 7 unset** (74% / 26% of the 128 with a value). That number is real but narrow: it is the *last successful* tool per pantry. Failures are never written (persist only runs on success), each refresh overwrites the previous value, and `source_metrics` records success rate and latency per source but not which tool was used. So there was no per-attempt record, no failure count, and no history — nothing that answers "how often does the primary scraper need help?"

The same `ScraperService` runs in two processes with opposite lifetimes: the API (long-lived Deployment, the discovery endpoint scrapes in-process) and the refresh agent (a CronJob pod that lives for minutes, fortnightly).

**Options Considered**:
| Criteria | Pull everywhere | Push everywhere (OTLP/remote-write) | Pull API + Pushgateway for the job |
|----------|-----------------|--------------------------------------|------------------------------------|
| Catches the CronJob | No — a 30s scrape interval misses a pod that exits between scrapes | Yes | Yes |
| Extra infrastructure | None | A collector | One small Deployment |
| Fits the API | Yes | Overkill | Yes |
| Prometheus's own guidance | — | — | The documented use case for the Pushgateway: service-level batch jobs |

**Decision**: Pull for the API, push for the job. Specifically:

- **Two counters, not one.** `equitable_scrape_attempts_total{method,outcome}` counts every tool *tried*; `equitable_scrape_results_total{method}` counts the tool that *won* per URL (including `none`). Results is the split. `jina attempts / crawl4ai attempts` is the fallback trigger rate — which differs from the split, because a Jina attempt can itself fail.
- **Outcomes derive from return values only** (`success` ≥ `MIN_CONTENT_CHARS`, `insufficient`, `failed`), and recording sits outside the decision logic, so instrumentation cannot change which tool wins. Every recording call swallows its own exceptions — tested by making the registry raise mid-scrape.
- **The API serves `/metrics` on a separate port (9464), not a FastAPI route.** The Ingress forwards every path on the `http` port, so a route would publish metrics to the internet. Verified: `https://equitable.localtest.me/metrics` → 404; a pod in `default` times out on 9464; only Prometheus's pods in `monitoring` are allowed by NetworkPolicy. The listener only starts when `METRICS_PORT` is set, so local dev, Render and the test suite are unchanged.
- **The agent pushes once, at the end, grouped by `run_id`.** A constant grouping key would make each run overwrite the last; per-run groups make `sum by (method)(...)` the cumulative split across every run the gateway holds. Cardinality is ~26 groups a year. `PUSHGATEWAY_URL` unset → no-op; push failure → a warning, never a failed run.
- **A project-owned `CollectorRegistry`.** The push carries only project metrics (not the pusher's `process_*`), and tests read values without global-state noise. The API's scrape endpoint merges it with the default registry so `process_resident_memory_bytes` sits next to the 2Gi limit.

**Consequences**:

- Verified end-to-end on kind: a capped run (2 sources, $0.05 of Gemini) pushed `results{crawl4ai}=1, results{jina}=1` and `attempts{crawl4ai,insufficient}=1` — Crawl4AI came back short on one site and Jina took over — all visible in Prometheus with `job`/`run_id` intact.
- **A crashed pod's attempts are not counted.** It never reaches the push. The resumed pod (same `run_id`, ADR-024) pushes and replaces the group. The durable per-pantry record is still `scrape_method` in Mongo; Prometheus is the operational view, not the ledger.
- The Pushgateway is a single point where the job's metrics live until scraped, and it forgets on restart unless persisted — hence its 1Gi PVC. It also never expires groups; that is fine at 26/year and would not be for a per-minute job.
- The résumé number should come from the dashboard once real fortnightly runs accumulate. Until then, the defensible statement is the Mongo aggregation above, worded as "share of pantries", not "share of attempts".

**Re-evaluation trigger**: If the job ever runs often (hourly or more), stop grouping by `run_id` and push to a constant group with `pushadd`, or move the job to OTLP. If a third scraper tool is added, it gets metrics for free — the label is the fetcher's `name`.

---

## ADR-031: kube-prometheus-stack on kind, Trimmed

**Date**: 2026-09-19
**Status**: Accepted

**Context**: ADR-030 needs a Prometheus, a Grafana, and kube-state-metrics (the only way to see "the refresh Job failed" after its pod is gone). It has to run on the same laptop kind cluster at $0.

**Options Considered**:
| Criteria | Hand-written Prometheus/Grafana manifests | kube-prometheus-stack (Helm) | Grafana Cloud free tier |
|----------|------------------------------------------|------------------------------|-------------------------|
| Scrape config lives next to the workload | No — one central prometheus.yml | Yes — ServiceMonitor CRDs | Via an agent |
| Industry-standard | No | Yes | Yes |
| Cost / data leaves laptop | $0 / no | $0 / no | $0 within limits / yes |
| Footprint on kind | Smallest | ~1 GiB after trimming | Agent only |

**Decision**: kube-prometheus-stack, chart pinned (91.4.1), heavily trimmed:

- **Off**: Alertmanager (nowhere to page at $0 — the project's rules still evaluate and show at `/alerts`), node-exporter (describes OrbStack's VM, not this project), etcd/scheduler/controller-manager/kube-proxy scraping (kind binds them to localhost, so they would be permanently DOWN targets that train you to ignore red), the ~200 default rules and default dashboards (written for production control planes).
- **`*SelectorNilUsesHelmValues: false`** so ServiceMonitors and rules in the app namespace are picked up without carrying the monitoring release's label.
- **Grafana admin password is generated in-cluster** by the setup script (`openssl rand`) into a Secret. The chart's fallback (`prom-operator`) is public.
- **The dashboard is JSON in the repo**, loaded by the Grafana sidecar from a labelled ConfigMap — not clicked together in a UI and lost with the cluster.
- **Four alert rules**, the non-obvious one being `EquiTableRefreshJobFailed` on `kube_job_failed{condition="true"}`, *not* `kube_job_status_failed`: the latter counts failed pods, and a crash-then-resume (the case ADR-024 exists for) has a failed pod inside a Job that succeeded. Alerting on it would page on recovery working.

**Consequences**:

- All 17 targets UP on first install, including both API pods through the new NetworkPolicy.
- The dashboard immediately surfaced something real: *Next scheduled run* read **−4.5 days**. The laptop cluster was off at 08:00 UTC on Sep 15, `startingDeadlineSeconds` (1h) expired, and `concurrencyPolicy: Forbid` drops rather than queues — so that fortnight's run simply did not happen. This is the strongest argument in the repo that a laptop is not a production scheduler, and it is now visible rather than silent. The panel goes red when negative.
- Prometheus storage is an emptyDir (30d retention). Losing it loses graphs, not data — the Pushgateway PVC and Mongo hold the rest.

**Re-evaluation trigger**: On a real cluster, turn Alertmanager back on with a receiver, give Prometheus a PVC, and re-enable node-exporter. If memory on the laptop becomes a problem, drop Grafana first — Prometheus's own UI answers every question the dashboard does.

---

## Template for New Decisions

```markdown
## ADR-NNN: [Title]

**Date**: YYYY-MM-DD
**Status**: Proposed | Accepted | Superseded by ADR-XXX | Deprecated

**Context**: Why this decision is needed.

**Options Considered**:
| Criteria | Option A | Option B | Option C |
|----------|----------|----------|----------|

**Decision**: What was chosen and why.

**Consequences**: What changes. What are the tradeoffs. What triggers re-evaluation.
```
