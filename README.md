# EquiTable

AI-powered food pantry discovery platform. Searches for food pantries near any location, scrapes their websites, extracts structured data via Gemini LLM, and displays everything on an interactive Google Map with real-time streaming updates.

## How It Works

1. **Search any location** — Type a city or address into the map search bar
2. **Auto-discovery triggers** — When the map viewport has fewer than 3 pantries, discovery kicks in automatically
3. **Google Places API** finds food pantries — Runs 4 search queries ("food bank", "food pantry", "food distribution", "community food"), deduplicates by place ID
4. **Crawl4AI scrapes** each pantry's website — Async headless browser extracts page content as markdown
5. **Gemini 2.0 Flash extracts** structured data — Hours, eligibility, ID requirements, status, confidence score (1-10)
6. **Results stream live via SSE** — Pantry markers appear on the map in real-time as each one is processed
7. **Places without websites** are stored with basic Google data (confidence=3, "Limited info" flag)
8. **7-day cache** prevents redundant API calls for the same area

## Features

- **Live Discovery** — Real-time food pantry discovery for any location in the US
- **Multi-Query Search** — 4 Google Places queries per discovery for maximum coverage
- **Place Details Fallback** — If a place has no website in search results, tries the Place Details API
- **AI Extraction** — Gemini 2.0 Flash extracts hours, eligibility, requirements from scraped HTML
- **Confidence Scoring** — Each pantry gets a 1-10 confidence score based on data quality
- **Interactive Map** — Google Maps with clustered markers, info windows, geospatial filtering
- **Viewport-Based Auto-Discovery** — Discovers pantries automatically when panning to new areas
- **SSE Streaming** — Server-Sent Events stream discovery progress in real-time
- **Geospatial Queries** — MongoDB 2dsphere indexes for fast nearby searches
- **Multi-City Support** — City/state filtering, seed data for major US cities
- **Result Caching** — 7-day MongoDB TTL cache on Places API results

## Project Structure

```
EquiTable/
├── backend_ml/                 # FastAPI backend
│   ├── main.py                 # API routes + rate limiter
│   ├── config.py               # Centralized environment settings
│   ├── database.py             # MongoDB Atlas connection + indexes
│   ├── models/
│   │   ├── pantry.py           # Pantry data model + GeoJSON
│   │   └── discovery.py        # Discovery job status + PlaceResult
│   ├── services/
│   │   ├── places_client.py    # Google Places API (multi-query + cache)
│   │   ├── discovery_service.py # Orchestrator: Places → dedup → scrape → store → SSE
│   │   ├── ingestion_pipeline.py # Crawl4AI → Gemini → Validator pipeline
│   │   ├── scraper.py          # Crawl4AI async web scraper
│   │   ├── extractor.py        # Gemini LLM structured extraction
│   │   └── validator.py        # Field-level validation rules
│   ├── prompts/                # LLM system/example prompts
│   ├── tests/                  # 142 backend tests
│   └── requirements.txt
├── frontend/                   # React 19 + Vite 7
│   └── src/
│       ├── components/
│       │   ├── MapExperience.jsx      # Main map view with discovery integration
│       │   ├── PantryMapClean.jsx     # Google Map with markers + info windows
│       │   ├── PlaceSearchControl.jsx # Google Places Autocomplete on map
│       │   ├── DiscoveryOverlay.jsx   # Radar animation during discovery
│       │   ├── CitySelector.jsx       # City picker overlay
│       │   └── MapOverlay.jsx         # Stats overlay on map
│       ├── hooks/
│       │   ├── useViewportDiscovery.js # Auto-discovery on map pan/zoom
│       │   └── useDiscovery.js         # Discovery API + SSE hook
│       ├── services/
│       │   └── discoveryService.js     # Discovery API client
│       ├── pages/
│       │   └── UnifiedPage.jsx         # Single-page app layout
│       └── __tests__/                  # 104 frontend tests
├── docs/
│   ├── decisions.md            # Architecture Decision Records (ADR-001 to ADR-014)
│   └── seed-strategy.md        # Multi-city expansion plan
└── README.md
```

## Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB Atlas account (free M0 tier works)
- Google Cloud project with:
  - Maps JavaScript API enabled
  - Places API (New) enabled
- Google Gemini API key

## Getting Started

### Backend Setup

```bash
cd backend_ml
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys (see Environment Variables below)
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The app will be at `http://localhost:5173` with the API at `http://127.0.0.1:8000`.

## Environment Variables

### Backend (`backend_ml/.env`)

```bash
MONGO_URI=mongodb+srv://...          # MongoDB Atlas connection string
DATABASE_NAME=equitable              # Database name (default: equitable)
GEMINI_API_KEY=AIza...               # Google Gemini API key
GOOGLE_PLACES_API_KEY=AIza...        # Google Places API key (same GCP project as Maps)
```

### Frontend (`frontend/.env`)

```bash
VITE_GOOGLE_MAPS_KEY=AIza...         # Google Maps JavaScript API key
VITE_API_URL=http://127.0.0.1:8000   # Backend API URL
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check |
| GET | `/pantries` | List pantries (optional `?city=X&state=Y` filter) |
| GET | `/pantries/nearby` | Geospatial search (`?lat=X&lng=Y&radius=Z`) |
| GET | `/cities` | City list with counts and map centers |
| POST | `/pantries/discover` | Start discovery job (returns `job_id` + SSE stream URL) |
| GET | `/pantries/discover/stream/{job_id}` | SSE event stream for live discovery progress |
| GET | `/pantries/discover/status/{job_id}` | Polling fallback for discovery status |
| POST | `/pantries/{id}/ingest` | Re-scrape + extract a single pantry |

## Testing

```bash
# Backend — 142 tests
cd backend_ml
source venv/bin/activate
python -m pytest tests/ -v

# Frontend — 104 tests
cd frontend
npm run test
```

## Tech Stack

### Backend
- **FastAPI** — Async Python web framework
- **Motor** — Async MongoDB driver
- **Crawl4AI** — Headless browser scraper (replaced Firecrawl)
- **Google Gemini 2.0 Flash** — LLM extraction (replaced OpenAI)
- **Google Places API (New)** — Food pantry discovery
- **SSE-Starlette** — Server-Sent Events for real-time streaming
- **httpx** — Async HTTP client for Google APIs

### Frontend
- **React 19** + **Vite 7** — UI framework + build tool
- **Tailwind CSS 4** — Utility-first styling
- **@vis.gl/react-google-maps** — Google Maps React wrapper
- **Framer Motion** — Animations (discovery overlay, marker transitions)
- **Vitest** — Test runner

### Infrastructure
- **MongoDB Atlas** — Database with 2dsphere geospatial indexes (free M0 tier)
- **Vercel** — Frontend hosting
- **Render** — Backend hosting

## Cost

All services are on free tiers. Current monthly cost: **$0**.

| Service | Free Limit | Cost After |
|---------|-----------|------------|
| Google Places API | 1,000 requests/month | $32/1K requests |
| Google Maps JS | $200/month credit | $7/1K loads |
| Gemini 2.0 Flash | 15 RPM, 1M tokens/day | $0.075/1M input |
| MongoDB Atlas M0 | 512MB storage | ~$9/month for M2 |
| Render | 750 hours/month | $7/month always-on |
| Vercel | Hobby tier | $20/month Pro |

## Architecture Decisions

Key decisions are documented in `docs/decisions.md` (ADR-001 through ADR-014). Highlights:

- **ADR-008**: Crawl4AI replaces Firecrawl as primary scraper ($0 cost vs $0.01/page)
- **ADR-011**: Google Places API (New) for pantry discovery
- **ADR-012**: SSE for real-time discovery streaming
- **ADR-014**: Multi-query Places search with 7-day caching

## License

MIT
