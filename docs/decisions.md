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
