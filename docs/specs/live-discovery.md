# Live Discovery: Real-Time Pantry Scraping on Search

**Author**: Planner + Tech Advisor Agent
**Date**: 2026-02-16
**Status**: Proposed
**Dependencies**: Phase 2 (Scraping Quality Overhaul) ✅, Phase 1 (Multi-City) ✅
**ADRs**: ADR-011 (Google Places for URL Discovery), ADR-012 (SSE for Streaming)

---

## Problem

EquiTable currently only serves pantries that were pre-seeded by developers. If a user searches for a location outside our 5 Tier 1 cities, they see nothing. The seed strategy doc (Tier 3) says: "All other cities rely on live async discovery." This spec defines that system.

## User Story

> As a user searching for food pantries in a new area, I want the system to automatically discover and scrape nearby pantries in real time, so I don't have to wait for a developer to manually add my city.

## UX Flow

1. User types a location (city name, address, or zip code) in the map search bar
2. Backend checks for fresh data in that area (< 24h old pantries within radius)
3. **If fresh data exists**: Return it immediately — no discovery needed
4. **If no/stale data**: Kick off a discovery job
   - Frontend shows: `"Discovering pantries near [location]..."` with animated progress
   - Backend finds pantry URLs via Google Places API
   - Each URL is scraped → extracted → validated → stored
   - Results stream to frontend via SSE — markers appear one by one on the map
   - When complete: `"Found 8 pantries near [location]"` with a subtle toast
5. If some URLs fail: `"Found 6 pantries (2 couldn't be loaded)"` — partial results are fine

---

## Technology Decisions

### Decision 1: URL Discovery — Google Places Text Search (New)

See **ADR-011** in `docs/decisions.md` for the full evaluation.

**Summary**: Use Google Places API (New) `Text Search` with the query `"food pantry" OR "food bank"` near the target location. This returns structured business data including `websiteUri`, `formattedAddress`, and `location` (lat/lng).

**Key facts**:
- Enterprise tier (needed for `websiteUri` field): **1,000 free requests/month**, then $35/1,000
- At ~1-3 discovery searches per day, we use ~30-90 requests/month — well within free tier
- Each Text Search returns up to 20 results; we cap at 10 per discovery job
- Results include lat/lng and address, eliminating the need for separate geocoding

**Evaluation table**:

| Criteria | Google Places Text Search | Google Custom Search | SerpAPI | Yelp Fusion |
|----------|--------------------------|---------------------|---------|-------------|
| Free tier | 1,000/mo (Enterprise) | Closed to new users | 100/mo | None ($7.99/1K) |
| Returns website URL | Yes (`websiteUri`) | Indirectly (search results) | Indirectly | Sometimes |
| Returns lat/lng | Yes | No | No | Yes |
| Result quality for pantries | Excellent (structured) | Poor (mixed with directories) | Poor (mixed) | Poor coverage |
| Cost at scale | $35/1K requests | $5/1K | $75/mo for 5K | $7.99/1K |
| Setup complexity | Medium (Google Cloud) | N/A | Low | Low |

**Fallback**: For pantries found by Places API that lack a `websiteUri`, store them with basic info (name, address, lat/lng) and `confidence: 3` (Places API data only, no scrape).

### Decision 2: Streaming — Server-Sent Events (SSE)

See **ADR-012** in `docs/decisions.md` for the full evaluation.

**Summary**: Use SSE via the `sse-starlette` library on the backend and native `EventSource` on the frontend. SSE is the simplest option for server→client streaming, requires no WebSocket infrastructure, and auto-reconnects.

**Evaluation table**:

| Criteria | SSE | WebSockets | Polling |
|----------|-----|------------|---------|
| Complexity | Low | High | Low |
| Real-time feel | Excellent | Excellent | Poor (2s delay) |
| Server library | `sse-starlette` (mature) | `websockets` + connection manager | None needed |
| Client API | Native `EventSource` | `WebSocket` + reconnection logic | `setInterval` + fetch |
| Proxy/CDN compat | Good (HTTP/1.1) | Needs upgrade support | Excellent |
| Bidirectional | No (server→client only) | Yes | No |
| Auto-reconnect | Built-in | Must implement | N/A |
| Render.com compat | Yes | Yes (but cold starts kill connections) | Yes |

**Why not polling**: Discovery takes 30-60 seconds. With 2-second polling, users see results appear in chunks rather than one-by-one. SSE gives a premium feel for minimal extra complexity.

**Why not WebSockets**: Overkill — we only need server→client events. WebSockets add connection management, heartbeats, and reconnection logic. Render's free tier cold starts also break WebSocket connections.

### Decision 3: Abuse Prevention

| Control | Implementation |
|---------|---------------|
| Rate limit | 3 discovery jobs per IP per hour (via in-memory counter + TTL) |
| Max URLs per job | 10 (even if Places API returns 20) |
| Viewport bounds validation | Reject if bounds span > 100km (prevents "discover the entire US") |
| Concurrent job limit | 1 active job per IP (return existing `job_id` if already running) |
| Freshness dedup | Skip any URL already in DB with `last_updated` < 24h ago |
| Source URL dedup | Skip any URL already being processed in another active job |

### Decision 4: Failure Handling

| Scenario | Behavior |
|----------|----------|
| Places API returns 0 results | SSE event: `{"event": "complete", "found": 0, "message": "No food pantries found in this area"}` |
| Places API fails | SSE event: `{"event": "error", "message": "Couldn't search this area. Try again later."}` + HTTP 502 on initial POST |
| 3/5 scrapes fail | Show the 2 that succeeded. SSE event per failure: `{"event": "pantry_failed", "url": "..."}`. Final: `{"event": "complete", "found": 2, "failed": 3}` |
| All scrapes fail | `{"event": "complete", "found": 0, "failed": 5, "message": "Found locations but couldn't load their websites"}` |
| Gemini API down | Extraction fails → treat as scrape failure. Store basic Places API data (name/address/lat/lng) with `confidence: 3` |
| Client disconnects mid-stream | Backend detects disconnect via `request.is_disconnected()`, cancels remaining scrapes, keeps already-stored results |
| Job times out (> 120s) | Force-complete with partial results. SSE event: `{"event": "complete", "timed_out": true}` |

---

## Database Changes

### New Collection: `discovery_jobs`

Tracks active and recent discovery jobs for deduplication, rate limiting, and status.

```javascript
{
  _id: ObjectId,
  job_id: string,              // UUID — used in API URLs
  status: "running" | "completed" | "failed" | "timed_out",

  // Search parameters
  query: string,               // Original search text (e.g. "Denver, CO")
  center: {                    // Geocoded center of search
    lat: number,
    lng: number
  },
  radius_meters: number,       // Search radius (default 8000 = ~5 miles)

  // Progress tracking
  urls_found: number,          // Total URLs from Places API
  urls_processed: number,      // Completed (success or fail)
  urls_succeeded: number,      // Successfully scraped + stored
  urls_failed: number,         // Failed scrape/extract/validate
  pantry_ids: [ObjectId],      // IDs of pantries created/updated

  // Metadata
  client_ip: string,           // For rate limiting
  created_at: datetime,
  completed_at: datetime | null,
  duration_ms: number | null,

  // Error details (if status = "failed")
  error: string | null
}
```

**Indexes**:
- `job_id` (unique) — for lookups
- `client_ip, created_at` (compound) — for rate limiting queries
- `status, created_at` (compound) — for cleanup of old jobs
- `center` (2dsphere on `{"center.type": "Point", "center.coordinates": [lng, lat]}`) — optional, for finding overlapping jobs
- TTL index on `created_at` with expiry of 7 days — auto-cleanup old jobs

### Modified Collection: `pantries`

Add one new field:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `discovered_via` | `Optional[str]` | `null` | `"seed"`, `"discovery"`, or `null` (legacy) |

Existing fields used by discovery:
- `source_url` (unique sparse index) — prevents duplicate scrapes
- `last_updated` — freshness check
- `city`, `state` — set from Places API response or geocoded
- `confidence` — set by extraction pipeline

---

## API Contracts

### `POST /pantries/discover`

Starts a discovery job. Returns immediately with a job ID and SSE stream URL.

**Request**:
```json
{
  "query": "Denver, CO",
  "lat": 39.7392,
  "lng": -104.9903,
  "radius_meters": 8000
}
```

- `query`: Human-readable location string (used in Places API search)
- `lat`, `lng`: Center of search area (from Google Maps geocoder on frontend)
- `radius_meters`: Optional, default 8000 (~5 miles), max 50000

**Response (201 Created)**:
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "running",
  "stream_url": "/pantries/discover/stream/a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "existing_pantries": 2
}
```

- `existing_pantries`: Number of fresh pantries already in DB for this area (returned immediately via the normal `/pantries/nearby` endpoint)

**Error responses**:

| Status | Body | Condition |
|--------|------|-----------|
| 400 | `{"detail": "Invalid coordinates"}` | lat/lng out of range |
| 400 | `{"detail": "Radius too large (max 50km)"}` | radius_meters > 50000 |
| 429 | `{"detail": "Discovery rate limit exceeded. Try again in N minutes."}` | > 3 jobs/hour from this IP |
| 409 | `{"detail": "Discovery already running", "job_id": "...", "stream_url": "..."}` | Active job for this IP |
| 502 | `{"detail": "Could not search for pantries in this area"}` | Places API failure |

### `GET /pantries/discover/stream/{job_id}`

SSE endpoint. Returns a stream of events as pantries are discovered.

**Headers**: `Content-Type: text/event-stream`

**Event types**:

```
event: job_started
data: {"job_id": "...", "query": "Denver, CO", "urls_found": 8}

event: pantry_discovered
data: {"pantry_id": "...", "name": "Denver Rescue Mission", "address": "1130 Park Ave W", "lat": 39.7434, "lng": -105.0003, "status": "OPEN", "confidence": 8, "source_url": "https://..."}

event: pantry_skipped
data: {"source_url": "https://...", "reason": "already_fresh"}

event: pantry_failed
data: {"source_url": "https://...", "stage": "scrape", "reason": "Timeout after 30s"}

event: progress
data: {"processed": 5, "total": 8, "succeeded": 4, "failed": 1}

event: complete
data: {"job_id": "...", "found": 6, "failed": 2, "skipped": 1, "duration_ms": 45200, "timed_out": false}

event: error
data: {"message": "Discovery failed unexpectedly"}
```

**Connection behavior**:
- Stream stays open until `complete` or `error` event
- If client disconnects, backend cancels remaining work but keeps stored results
- If job already completed when client connects, immediately sends `complete` event with summary
- Heartbeat: empty comment (`: heartbeat`) every 15 seconds to keep connection alive

### `GET /pantries/discover/status/{job_id}`

Fallback polling endpoint (for clients that can't use SSE, e.g. behind certain proxies).

**Response**:
```json
{
  "job_id": "...",
  "status": "running",
  "urls_found": 8,
  "urls_processed": 5,
  "urls_succeeded": 4,
  "urls_failed": 1,
  "pantry_ids": ["...", "...", "...", "..."],
  "created_at": "2026-02-16T12:00:00Z",
  "duration_ms": 23000
}
```

When `status` is `"completed"`:
```json
{
  "job_id": "...",
  "status": "completed",
  "urls_found": 8,
  "urls_processed": 8,
  "urls_succeeded": 6,
  "urls_failed": 2,
  "pantry_ids": ["...", "...", "...", "...", "...", "..."],
  "created_at": "2026-02-16T12:00:00Z",
  "completed_at": "2026-02-16T12:00:45Z",
  "duration_ms": 45200
}
```

---

## Data Flow

### Step-by-step: User search → Markers on map

```
┌─────────────────────────────────────────────────────────────────┐
│ FRONTEND                                                         │
│                                                                   │
│  1. User types "Denver, CO" in search bar                        │
│  2. Google Maps Geocoding resolves → lat: 39.7392, lng: -104.99  │
│  3. Map centers on Denver                                        │
│  4. GET /pantries/nearby?lat=39.73&lng=-104.99&max_distance=8000 │
│     → Returns 0 pantries (no seeded data for Denver)             │
│  5. UI shows "No pantries found. Discover pantries nearby?"      │
│     with a [Discover] button                                     │
│  6. User clicks [Discover]                                       │
│  7. POST /pantries/discover                                      │
│     body: { query: "Denver, CO", lat: 39.7392, lng: -104.99 }   │
│  8. Response: { job_id: "abc", stream_url: "/...stream/abc" }    │
│  9. Open EventSource(stream_url)                                 │
│ 10. Show "Discovering pantries near Denver..." with spinner      │
│                                                                   │
│  On each `pantry_discovered` event:                              │
│  11. Add marker to map with pop-in animation                     │
│  12. Add pantry to sidebar list                                  │
│  13. Update progress: "Found 3 so far..."                        │
│                                                                   │
│  On `complete` event:                                            │
│  14. Close EventSource                                           │
│  15. Show toast: "Found 6 pantries near Denver"                  │
│  16. Transition to normal map view                               │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ BACKEND                                                          │
│                                                                   │
│  7. POST /pantries/discover received                             │
│     a. Validate coordinates + rate limit check                   │
│     b. Check for existing fresh pantries (< 24h) in radius      │
│     c. Create discovery_job document (status: "running")         │
│     d. Launch background task: run_discovery(job_id)             │
│     e. Return 201 with job_id + stream_url                      │
│                                                                   │
│  Background task: run_discovery(job_id)                          │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ PHASE 1: URL Discovery                                      │ │
│  │  a. Call Google Places Text Search:                          │ │
│  │     query: "food pantry OR food bank"                        │ │
│  │     locationBias: { circle: { center, radius } }             │ │
│  │  b. Extract up to 10 results with websiteUri                │ │
│  │  c. For each result:                                         │ │
│  │     - Check source_url uniqueness vs DB                      │ │
│  │     - If exists + fresh (< 24h): emit `pantry_skipped`      │ │
│  │     - If exists + stale: add to scrape queue                 │ │
│  │     - If new: add to scrape queue with Places metadata       │ │
│  │  d. Emit `job_started` with urls_found count                │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ PHASE 2: Parallel Scraping (max 3 concurrent)               │ │
│  │  For each URL in scrape queue:                               │ │
│  │   a. ScraperService.scrape_url(url)                         │ │
│  │      → Returns markdown or None                              │ │
│  │   b. If scrape succeeded:                                    │ │
│  │      ExtractorService.extract(markdown)                     │ │
│  │      → Returns structured dict                               │ │
│  │   c. validate_extraction(dict)                              │ │
│  │      → Returns validated dict or raises                     │ │
│  │   d. Merge Places API metadata + extraction:                │ │
│  │      - name, address, lat, lng from Places (authoritative)  │ │
│  │      - status, hours, eligibility from Gemini (extracted)   │ │
│  │      - city, state from geocoded/Places address             │ │
│  │      - source_url, discovered_via="discovery"               │ │
│  │   e. Upsert to pantries collection (by source_url)          │ │
│  │   f. Emit `pantry_discovered` SSE event                     │ │
│  │   g. On failure: emit `pantry_failed`, continue             │ │
│  │   h. Emit `progress` after each URL                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ PHASE 3: Completion                                          │ │
│  │  a. Update discovery_job: status="completed", stats          │ │
│  │  b. Emit `complete` SSE event                               │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Sequence Diagram (simplified)

```
User          Frontend              Backend              Places API    Crawl4AI    Gemini
 │               │                     │                     │            │          │
 │ search "Denver"                     │                     │            │          │
 │──────────────>│                     │                     │            │          │
 │               │ GET /pantries/nearby │                     │            │          │
 │               │────────────────────>│                     │            │          │
 │               │       [] (empty)    │                     │            │          │
 │               │<────────────────────│                     │            │          │
 │  "No pantries"│                     │                     │            │          │
 │<──────────────│                     │                     │            │          │
 │               │                     │                     │            │          │
 │ click Discover│                     │                     │            │          │
 │──────────────>│                     │                     │            │          │
 │               │ POST /discover      │                     │            │          │
 │               │────────────────────>│                     │            │          │
 │               │  { job_id, stream } │                     │            │          │
 │               │<────────────────────│                     │            │          │
 │               │                     │                     │            │          │
 │               │ EventSource(stream) │                     │            │          │
 │               │────────────────────>│ Text Search         │            │          │
 │               │                     │────────────────────>│            │          │
 │               │                     │  10 results         │            │          │
 │               │                     │<────────────────────│            │          │
 │               │  SSE: job_started   │                     │            │          │
 │               │<────────────────────│                     │            │          │
 │  "Discovering"│                     │                     │            │          │
 │<──────────────│                     │                     │            │          │
 │               │                     │ scrape(url_1)       │            │          │
 │               │                     │───────────────────────────────>│  │          │
 │               │                     │ scrape(url_2)       │            │          │
 │               │                     │───────────────────────────────>│  │          │
 │               │                     │ scrape(url_3)       │            │            │
 │               │                     │───────────────────────────────>│  │          │
 │               │                     │        markdown_1   │            │          │
 │               │                     │<───────────────────────────────│  │          │
 │               │                     │ extract(markdown_1) │            │          │
 │               │                     │──────────────────────────────────────────>│
 │               │                     │        pantry_data  │            │          │
 │               │                     │<──────────────────────────────────────────│
 │               │                     │ validate + store    │            │          │
 │               │ SSE: pantry_discovered                    │            │          │
 │               │<────────────────────│                     │            │          │
 │  marker pops  │                     │                     │            │          │
 │  on map       │                     │                     │            │          │
 │<──────────────│                     │                     │            │          │
 │               │                     │  ... (repeat) ...   │            │          │
 │               │ SSE: complete       │                     │            │          │
 │               │<────────────────────│                     │            │          │
 │  "Found 6!"   │                     │                     │            │          │
 │<──────────────│                     │                     │            │          │
```

---

## Component Tree

### Backend

```
main.py
├── POST /pantries/discover          → DiscoveryService.start_job()
├── GET  /pantries/discover/stream/  → DiscoveryService.stream_events()
└── GET  /pantries/discover/status/  → DiscoveryService.get_status()

services/
├── discovery_service.py    [NEW]
│   ├── DiscoveryService
│   │   ├── start_job(query, lat, lng, radius) → job_id
│   │   ├── run_discovery(job_id) → async generator of SSE events
│   │   ├── stream_events(job_id, request) → EventSourceResponse
│   │   ├── get_status(job_id) → dict
│   │   └── _check_rate_limit(client_ip) → bool
│   └── Uses:
│       ├── PlacesClient (URL discovery)
│       ├── IngestionPipeline (existing: scrape→extract→validate)
│       └── MongoDB (discovery_jobs + pantries collections)
│
├── places_client.py        [NEW]
│   └── PlacesClient
│       ├── search_nearby(query, lat, lng, radius) → list[PlaceResult]
│       └── PlaceResult: { name, address, lat, lng, website_url, place_id }
│
├── ingestion_pipeline.py   [EXISTING — no changes needed]
├── scraper.py              [EXISTING — no changes needed]
├── extractor.py            [EXISTING — no changes needed]
└── validator.py            [EXISTING — no changes needed]

models/
└── discovery.py            [NEW]
    ├── DiscoveryRequest     (Pydantic: query, lat, lng, radius_meters)
    ├── DiscoveryResponse    (Pydantic: job_id, status, stream_url, existing_pantries)
    ├── DiscoveryStatus      (Pydantic: full job status)
    └── DiscoveryJob         (Pydantic: DB document model)
```

### Frontend

```
components/
├── MapExperience.jsx       [MODIFIED — add discovery trigger + UI]
│   ├── DiscoveryBanner     [NEW — inline component]
│   │   └── "No pantries found. Discover nearby?" + [Discover] button
│   ├── DiscoveryProgress   [NEW — inline component]
│   │   └── "Discovering pantries near Denver..." + progress bar + count
│   └── Existing: sidebar, filters, map, detail panel
│
├── PantryMapClean.jsx      [MODIFIED — marker pop-in animation]

hooks/
├── useDiscovery.js         [NEW]
│   └── useDiscovery({ lat, lng })
│       ├── Returns: { discover, isDiscovering, progress, discoveredPantries, error, cancel }
│       ├── discover(query, radius) → starts POST + EventSource
│       ├── progress: { found, total, failed }
│       └── discoveredPantries: incrementally built array
│
├── usePantries.js          [EXISTING — no changes]
├── useNearbyPantries.js    [EXISTING — no changes]
└── useMapLazyLoad.js       [EXISTING — no changes]

services/
└── discoveryService.js     [NEW]
    ├── startDiscovery({ query, lat, lng, radius }) → { job_id, stream_url }
    └── getDiscoveryStatus(job_id) → status object
```

---

## Implementation Details

### Backend: `services/places_client.py`

```python
import httpx
import os
from dataclasses import dataclass

@dataclass
class PlaceResult:
    name: str
    address: str
    lat: float
    lng: float
    website_url: str | None
    place_id: str

class PlacesClient:
    """Thin wrapper around Google Places API (New) Text Search."""

    BASE_URL = "https://places.googleapis.com/v1/places:searchText"

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_PLACES_API_KEY")

    async def search_nearby(
        self,
        query: str,
        lat: float,
        lng: float,
        radius_meters: int = 8000,
        max_results: int = 10,
    ) -> list[PlaceResult]:
        """
        Search for food pantries/banks near a location.
        Uses Text Search (New) with Enterprise field mask for websiteUri.
        """
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": (
                "places.displayName,places.formattedAddress,"
                "places.location,places.websiteUri,places.id"
            ),
        }
        body = {
            "textQuery": f"food pantry OR food bank near {query}",
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_meters),
                }
            },
            "maxResultCount": max_results,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(self.BASE_URL, json=body, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()

        results = []
        for place in data.get("places", []):
            loc = place.get("location", {})
            results.append(PlaceResult(
                name=place.get("displayName", {}).get("text", "Unknown"),
                address=place.get("formattedAddress", ""),
                lat=loc.get("latitude", 0),
                lng=loc.get("longitude", 0),
                website_url=place.get("websiteUri"),
                place_id=place.get("id", ""),
            ))

        return results[:max_results]
```

### Backend: `services/discovery_service.py` (core logic)

```python
class DiscoveryService:
    MAX_CONCURRENT_SCRAPES = 3
    MAX_URLS_PER_JOB = 10
    RATE_LIMIT_PER_HOUR = 3
    JOB_TIMEOUT_SECONDS = 120

    async def start_job(self, request, client_ip) -> dict:
        # 1. Rate limit check
        # 2. Check for active job from this IP → 409 if exists
        # 3. Count existing fresh pantries in radius
        # 4. Create discovery_job document
        # 5. Launch run_discovery as background task
        # 6. Return job_id + stream_url + existing_pantries count

    async def run_discovery(self, job_id: str):
        # 1. Load job from DB
        # 2. Call PlacesClient.search_nearby()
        # 3. Filter out fresh duplicates (source_url in DB + < 24h)
        # 4. Emit job_started event
        # 5. Process URLs with asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)
        #    For each URL:
        #      a. IngestionPipeline.ingest(url) → PantryUpdate
        #      b. Merge with Places metadata (name, address, lat, lng, city, state)
        #      c. Upsert to pantries collection
        #      d. Emit pantry_discovered or pantry_failed
        #      e. Emit progress
        # 6. Update job status to completed
        # 7. Emit complete event

    async def stream_events(self, job_id: str, request: Request):
        # Returns EventSourceResponse from an async generator
        # Generator yields from an asyncio.Queue populated by run_discovery
        # Checks request.is_disconnected() for client disconnect
        # Sends heartbeat every 15 seconds
```

### Backend: SSE Event Queue Pattern

The `run_discovery` task and `stream_events` endpoint communicate via an `asyncio.Queue`:

```python
# In-memory job event queues (keyed by job_id)
_event_queues: dict[str, asyncio.Queue] = {}

async def run_discovery(self, job_id):
    queue = _event_queues[job_id] = asyncio.Queue()
    try:
        # ... discovery logic ...
        await queue.put({"event": "pantry_discovered", "data": {...}})
        # ... more logic ...
        await queue.put({"event": "complete", "data": {...}})
    finally:
        await queue.put(None)  # Sentinel to close stream

async def stream_events(self, job_id, request):
    queue = _event_queues.get(job_id)
    if not queue:
        # Job already completed — return summary from DB
        ...

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                if event is None:
                    break
                yield event
            except asyncio.TimeoutError:
                yield {"comment": "heartbeat"}

            if await request.is_disconnected():
                break

    return EventSourceResponse(event_generator())
```

### Frontend: `hooks/useDiscovery.js`

```javascript
export default function useDiscovery() {
  const [isDiscovering, setIsDiscovering] = useState(false)
  const [progress, setProgress] = useState(null)        // { found, total, failed }
  const [discoveredPantries, setDiscoveredPantries] = useState([])
  const [error, setError] = useState(null)
  const eventSourceRef = useRef(null)

  const discover = useCallback(async (query, lat, lng, radius = 8000) => {
    setIsDiscovering(true)
    setProgress(null)
    setDiscoveredPantries([])
    setError(null)

    try {
      // 1. Start the job
      const { job_id, stream_url } = await discoveryService.startDiscovery({
        query, lat, lng, radius_meters: radius,
      })

      // 2. Open SSE stream
      const es = new EventSource(`${API_BASE}${stream_url}`)
      eventSourceRef.current = es

      es.addEventListener('pantry_discovered', (e) => {
        const pantry = JSON.parse(e.data)
        setDiscoveredPantries((prev) => [...prev, pantry])
      })

      es.addEventListener('progress', (e) => {
        setProgress(JSON.parse(e.data))
      })

      es.addEventListener('complete', (e) => {
        const data = JSON.parse(e.data)
        setProgress({ found: data.found, total: data.found + data.failed, failed: data.failed })
        setIsDiscovering(false)
        es.close()
      })

      es.addEventListener('error', (e) => {
        setError('Discovery failed. Please try again.')
        setIsDiscovering(false)
        es.close()
      })

      es.onerror = () => {
        setError('Connection lost. Results may be incomplete.')
        setIsDiscovering(false)
        es.close()
      }
    } catch (err) {
      setError(err.message)
      setIsDiscovering(false)
    }
  }, [])

  const cancel = useCallback(() => {
    eventSourceRef.current?.close()
    setIsDiscovering(false)
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => eventSourceRef.current?.close()
  }, [])

  return { discover, isDiscovering, progress, discoveredPantries, error, cancel }
}
```

### Frontend: Discovery UI in MapExperience

The discovery UI integrates into the existing MapExperience sidebar:

```
┌─────────────────────────────────────────────────────────┐
│ MapExperience                                            │
│ ┌──────────────────────┬────────────────────────────────┐│
│ │ Sidebar              │ Map                             ││
│ │ ┌──────────────────┐ │                                 ││
│ │ │ Search bar       │ │                                 ││
│ │ └──────────────────┘ │                                 ││
│ │ ┌──────────────────┐ │   When empty + not discovering: ││
│ │ │ Filters          │ │   ┌─────────────────────────┐  ││
│ │ └──────────────────┘ │   │  No pantries found.     │  ││
│ │                      │   │  [Discover Nearby]      │  ││
│ │ IF discovering:      │   └─────────────────────────┘  ││
│ │ ┌──────────────────┐ │                                 ││
│ │ │ ● Discovering... │ │   When discovering:             ││
│ │ │ ████████░░ 6/10  │ │   markers appear with           ││
│ │ │ Found so far:    │ │   pop-in animation              ││
│ │ │  • Denver Rescue │ │                                 ││
│ │ │  • Food Bank...  │ │                                 ││
│ │ └──────────────────┘ │                                 ││
│ │                      │                                 ││
│ │ Normal pantry list:  │                                 ││
│ │  • Pantry A          │                                 ││
│ │  • Pantry B          │                                 ││
│ │  • ...               │                                 ││
│ └──────────────────────┴────────────────────────────────┘│
└─────────────────────────────────────────────────────────┘
```

**DiscoveryBanner** (shown when pantries list is empty and not discovering):
- Text: "No pantries found in this area"
- Button: "Discover Nearby Pantries" (emerald-500, prominent)
- Only shown when `pantries.length === 0 && !isDiscovering`

**DiscoveryProgress** (shown during active discovery):
- Animated pulse dot + "Discovering pantries near Denver..."
- Progress bar: `processed / total` with percentage
- Running count: "Found 4 so far..."
- Cancel button (subtle, text-only)

**Marker pop-in animation**: New markers from discovery use a scale-up + fade-in animation via Framer Motion `AnimatePresence` + `motion.div` wrapping the marker.

---

## Environment Variables

### New Backend Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_PLACES_API_KEY` | Yes (for discovery) | Google Cloud API key with Places API (New) enabled |

### Existing Variables (unchanged)

| Variable | Used By |
|----------|---------|
| `MONGO_URI` | All DB operations |
| `GEMINI_API_KEY` | Extraction pipeline |

---

## New Dependencies

### Backend

| Package | Version | Purpose |
|---------|---------|---------|
| `sse-starlette` | `^2.0` | SSE response support for FastAPI |

All other dependencies (Crawl4AI, google-genai, Motor, httpx) are already installed.

### Frontend

No new dependencies. `EventSource` is a native browser API.

---

## Testing Requirements

### Backend Agent Tests

**File: `tests/test_discovery_service.py`** (8+ tests)

| Test | Description |
|------|-------------|
| `test_start_job_returns_job_id` | POST /discover returns 201 with job_id and stream_url |
| `test_rate_limit_blocks_excess` | 4th request within 1 hour returns 429 |
| `test_concurrent_job_returns_409` | Second request while first is running returns 409 with existing job_id |
| `test_invalid_coordinates_returns_400` | lat=999 returns 400 |
| `test_radius_too_large_returns_400` | radius_meters=100000 returns 400 |
| `test_status_endpoint_returns_progress` | GET /discover/status/{id} returns current job state |
| `test_completed_job_status` | Completed job shows final counts |
| `test_unknown_job_returns_404` | GET /discover/status/fake-id returns 404 |

**File: `tests/test_places_client.py`** (4+ tests)

| Test | Description |
|------|-------------|
| `test_search_returns_results` | Mock Places API response → list of PlaceResult |
| `test_search_handles_no_results` | Empty response → empty list |
| `test_search_handles_missing_website` | Results without websiteUri → website_url=None |
| `test_search_respects_max_results` | 20 results from API → capped at max_results |

**File: `tests/test_discovery_integration.py`** (4+ tests, mock Places + scraper)

| Test | Description |
|------|-------------|
| `test_full_discovery_flow` | Mock Places → mock scraper → mock Gemini → pantry stored in DB |
| `test_skips_fresh_pantries` | Pantry with last_updated < 24h → emits pantry_skipped |
| `test_handles_scrape_failure` | One URL fails → other URLs still processed → partial results |
| `test_job_timeout` | Job exceeding 120s → force-completes with timed_out=true |

### Scraping Quality Agent Tests

No changes needed — the existing `IngestionPipeline` is used as-is.

### Frontend Data Agent Tests

**File: `__tests__/useDiscovery.test.jsx`** (8+ tests)

| Test | Description |
|------|-------------|
| `test_initial_state` | isDiscovering=false, progress=null, discoveredPantries=[] |
| `test_discover_starts_job` | Calling discover() makes POST request and opens EventSource |
| `test_pantry_discovered_event` | SSE pantry_discovered → adds to discoveredPantries array |
| `test_progress_event` | SSE progress → updates progress state |
| `test_complete_event` | SSE complete → isDiscovering=false, EventSource closed |
| `test_error_event` | SSE error → sets error message |
| `test_cancel_closes_stream` | Calling cancel() closes EventSource |
| `test_cleanup_on_unmount` | Unmounting hook closes EventSource |

**File: `__tests__/discoveryService.test.js`** (3+ tests)

| Test | Description |
|------|-------------|
| `test_start_discovery_calls_api` | Calls POST /pantries/discover with correct body |
| `test_handles_429_rate_limit` | 429 response → throws with rate limit message |
| `test_handles_409_existing_job` | 409 response → returns existing job_id |

### Frontend UI Agent Tests

**File: `__tests__/DiscoveryUI.test.jsx`** (5+ tests)

| Test | Description |
|------|-------------|
| `test_shows_discover_banner_when_empty` | Empty pantries → "No pantries found" + Discover button |
| `test_hides_banner_when_has_pantries` | Non-empty pantries → no Discover button |
| `test_shows_progress_during_discovery` | isDiscovering=true → progress bar visible |
| `test_shows_found_count` | progress.found=3 → "Found 3 so far..." |
| `test_cancel_button_calls_cancel` | Click cancel → cancel() called |

---

## Build Sequence

### Step 1: Backend — Models + Database (1 session)
1. Create `models/discovery.py` (DiscoveryRequest, DiscoveryResponse, DiscoveryStatus, DiscoveryJob)
2. Add `discovered_via` field to `Pantry` and `PantryCreate` in `models/pantry.py`
3. Add `discovery_jobs` collection indexes in `database.py`
4. Verify existing tests pass

### Step 2: Backend — Places Client (1 session)
5. Create `services/places_client.py`
6. Write `tests/test_places_client.py` (mock httpx, no real API calls)
7. Add `GOOGLE_PLACES_API_KEY` to config documentation

### Step 3: Backend — Discovery Service (1-2 sessions)
8. `pip install sse-starlette` + add to `requirements.txt`
9. Create `services/discovery_service.py` (DiscoveryService class)
10. Add routes to `main.py`: POST /discover, GET /discover/stream, GET /discover/status
11. Write `tests/test_discovery_service.py` (unit tests, mock dependencies)
12. Write `tests/test_discovery_integration.py` (mock Places + scraper, real DB)

### Step 4: Frontend — Data Layer (1 session)
13. Create `services/discoveryService.js`
14. Create `hooks/useDiscovery.js`
15. Write `__tests__/useDiscovery.test.jsx`
16. Write `__tests__/discoveryService.test.js`

### Step 5: Frontend — UI Integration (1 session)
17. Add DiscoveryBanner and DiscoveryProgress to `MapExperience.jsx`
18. Wire `useDiscovery` hook into MapExperience (merge discoveredPantries with existing pantries)
19. Add marker pop-in animation to `PantryMapClean.jsx`
20. Write `__tests__/DiscoveryUI.test.jsx`
21. Verify all frontend tests pass

### Step 6: Integration + Manual Testing (1 session)
22. Run full backend test suite
23. Run full frontend test suite
24. Manual test: search Denver → see "No pantries" → click Discover → watch markers appear
25. Verify freshness dedup: re-discover same area → skips recent pantries
26. Verify rate limiting: 4th discover in 1 hour → 429 error
27. Add ADR-011 and ADR-012 to `docs/decisions.md`

---

## Cost Estimate

| Resource | Monthly Usage (estimated) | Cost |
|----------|--------------------------|------|
| Google Places Text Search (Enterprise) | ~50-100 requests | **$0** (within 1,000 free/month) |
| Gemini 2.0 Flash extraction | ~200-500 extractions | **$0** (within free tier) |
| Crawl4AI scraping | Unlimited | **$0** (self-hosted) |
| MongoDB Atlas | <512MB | **$0** (free tier) |
| **Total** | | **$0/month** |

**Break-even point**: ~1,000 Places API requests/month (≈30 discovery searches/day). Beyond that, $35/1,000 requests.

---

## Open Questions

1. **Should discovery auto-trigger or require a button click?** This spec uses a button click (explicit user intent). Auto-triggering when the map viewport has no pantries is more seamless but risks burning Places API quota on casual map browsing. **Recommendation**: Start with button, evaluate auto-trigger later.

2. **Should we geocode the search query ourselves or require lat/lng from the frontend?** This spec requires lat/lng from the frontend (Google Maps Geocoder is already available client-side). This avoids adding server-side geocoding complexity and cost.

3. **How long do we keep discovery_jobs?** TTL of 7 days. Old jobs are auto-deleted. Pantries discovered are permanent.

4. **Should discovered pantries have a visual indicator?** Optional: a small badge or different marker outline for "recently discovered" pantries (< 1 hour old). Low priority — cosmetic only.
