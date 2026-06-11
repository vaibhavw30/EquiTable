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
**Status**: Accepted

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
