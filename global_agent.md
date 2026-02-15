# EquiTable — Global Agent Instructions

## Project Overview

EquiTable is an AI-powered food pantry discovery platform that autonomously scrapes pantry websites, uses LLM intelligence to extract structured data, and presents it on an interactive map. The core value proposition is **autonomous intelligence** — instead of manually maintaining pantry data, EquiTable scrapes websites and uses Gemini to extract structured, date-aware information.

## Architecture

```
User → Vercel (React 19 + Vite) → Render (FastAPI) → MongoDB Atlas
                                        ↓
                                  Firecrawl (scraping)
                                  Gemini 2.0 Flash (LLM extraction)
```

## Tech Stack

| Layer    | Technology                                    | Notes                                        |
| -------- | --------------------------------------------- | -------------------------------------------- |
| Frontend | React 19 + Vite 7                             | SPA, client-side routing via React Router 7  |
| Styling  | Tailwind CSS 4 + Framer Motion                | Utility-first + animation                    |
| Maps     | Google Maps API (`@vis.gl/react-google-maps`) | Markers, info windows, geolocation           |
| Backend  | FastAPI (Python 3.10+)                        | Async REST API with Motor for MongoDB        |
| Database | MongoDB Atlas                                 | Geospatial 2dsphere indexing, document store |
| AI/LLM   | Google Gemini 2.0 Flash                       | Structured extraction from scraped content   |
| Scraping | Firecrawl (evaluating alternatives)           | Website → clean Markdown                     |
| Deploy   | Vercel (frontend) + Render (backend)          | Serverless + PaaS                            |

## Project Structure

```
EquiTable/
├── AGENTS.md                          # THIS FILE — global context
├── agents/
│   ├── planner-tech-advisor.md        # Planner + Tech Advisor subagent
│   ├── scraping-quality.md            # Scraping & extraction quality subagent
│   ├── backend.md                     # Backend subagent
│   ├── frontend-ui.md                 # Frontend UI/UX + animation subagent
│   └── frontend-data.md              # Frontend data/integration subagent
├── docs/
│   ├── decisions.md                   # Architecture Decision Records (ADRs)
│   ├── seed-strategy.md               # Multi-city seed data plan
│   ├── error-monitoring.md            # Logging and error handling patterns
│   └── specs/                         # Feature specs produced by Planner agent
├── backend_ml/
│   ├── main.py                        # FastAPI entry point
│   ├── models/                        # Pydantic models
│   ├── services/                      # Business logic
│   ├── scripts/                       # Utility/ingestion scripts
│   ├── tests/                         # Backend test suite
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── hooks/
│   │   └── __tests__/
│   └── package.json
└── README.md
```

## Database Schema

Collection: `pantries`

```
Pantry {
  _id:               ObjectId
  name:              string
  address:           string
  city:              string              # NEW — multi-city support
  state:             string              # NEW
  lat/lng:           float               # backwards compat
  location:          GeoJSON Point       # { type: "Point", coordinates: [lng, lat] }
  hours_notes:       string
  hours_today:       string | null
  eligibility_rules: [string]
  inventory_status:  enum (HIGH | MEDIUM | LOW)
  status:            enum (OPEN | CLOSED | WAITLIST | UNKNOWN)
  is_id_required:    bool | null
  residency_req:     string | null
  special_notes:     string | null
  confidence:        int (1-10) | null
  source_url:        string | null
  last_updated:      datetime
  scraped_at:        datetime | null     # NEW — when last scraped
  scrape_method:     string | null       # NEW — which tool was used
}
```

Collection: `users` (planned)

```
User {
  _id:               ObjectId
  email:             string (unique)
  password_hash:     string
  display_name:      string
  created_at:        datetime
  points:            int
  badges:            [string]
  saved_pantries:    [ObjectId]
  contributions:     [{ type, pantry_id, timestamp }]
}
```

## API Contract (Current + Planned)

### Existing

| Method | Route                                              | Description                             |
| ------ | -------------------------------------------------- | --------------------------------------- |
| GET    | `/`                                                | Health check                            |
| GET    | `/api/test`                                        | Frontend connectivity test              |
| GET    | `/pantries`                                        | Get all pantries                        |
| GET    | `/pantries/nearby?lat=&lng=&max_distance=&status=` | Geospatial nearby search                |
| POST   | `/pantries/{pantry_id}/ingest`                     | Scrape → extract → store for one pantry |

### Planned

| Method | Route                                | Description                               |
| ------ | ------------------------------------ | ----------------------------------------- |
| POST   | `/pantries/discover`                 | Live async scrape for a map viewport/city |
| GET    | `/pantries/discover/status/{job_id}` | Poll scraping job progress                |
| GET    | `/pantries/city/{city}`              | Get pantries for a specific city          |
| POST   | `/auth/register`                     | User registration                         |
| POST   | `/auth/login`                        | User login (returns JWT)                  |
| GET    | `/auth/me`                           | Get current user profile                  |
| POST   | `/users/save-pantry/{pantry_id}`     | Save a pantry to user's list              |
| POST   | `/users/report/{pantry_id}`          | User reports outdated info (gamification) |
| GET    | `/users/leaderboard`                 | Top contributors                          |

## Global Conventions

### Code Style

- **Python**: Follow PEP 8. Use type hints everywhere. Async by default.
- **JavaScript/React**: Functional components only. Named exports for components, default export for pages. Use hooks.
- **Naming**: snake_case for Python, camelCase for JS, PascalCase for React components.

### Git

- Branch naming: `feature/<name>`, `fix/<name>`, `refactor/<name>`
- Commits: conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`)

### Error Handling

- Backend: Always return structured error responses `{ "detail": "message", "code": "ERROR_CODE" }`
- Frontend: Every API call must have error handling. Show user-friendly messages via toast/snackbar.

### Environment Variables

- Never commit secrets. Use `.env` files with `.env.example` templates.
- Backend: `GEMINI_API_KEY`, `FIRECRAWL_API_KEY`, `MONGODB_URI`, `JWT_SECRET` (planned)
- Frontend: `VITE_API_URL`, `VITE_GOOGLE_MAPS_KEY`

## Testing Philosophy

**Every subagent must include tests for any code it produces.** Tests are not optional — they are part of the deliverable.

### Backend Testing

- Framework: `pytest` + `pytest-asyncio` + `httpx` (for async FastAPI testing)
- Location: `backend_ml/tests/`
- Structure: Mirror the source structure (`tests/test_services/`, `tests/test_routes/`, etc.)
- Every new endpoint gets at minimum: 1 happy path test, 1 error/edge case test
- Every service function gets unit tests with mocked dependencies
- Scraping pipeline gets integration tests with fixture HTML/Markdown files

### Frontend Testing

- Framework: `vitest` + `@testing-library/react`
- Location: `frontend/src/__tests__/`
- Every new component gets: render test, key interaction test
- API service functions get tests with mocked fetch/axios
- Integration tests for critical flows (map loads → user searches → results appear)

### Test Commands

```bash
# Backend
cd backend_ml && python -m pytest tests/ -v

# Frontend
cd frontend && npm run test
```

### What Counts as "Not Breaking Core Features"

Before any PR or feature merge, these must pass:

1. Health check endpoint returns 200
2. `/pantries` returns valid pantry list
3. `/pantries/nearby` returns geospatially correct results
4. Frontend renders landing page without errors
5. Frontend renders map page and loads markers
6. Scraping pipeline produces valid structured output for at least 3 known test URLs
7. Confidence scores are within 1-10 range and non-null for scraped pantries

These are codified as the **smoke test suite** and must always pass.

## Subagent Coordination Rules

1. **Planner goes first.** No feature work begins without a spec from the Planner + Tech Advisor agent.
2. **API contracts are sacred.** If a backend change modifies a response shape, the spec must be updated first and the frontend data agent must be notified.
3. **No cross-boundary side effects.** Backend agent doesn't touch frontend code. Frontend agents don't modify backend code.
4. **Tests travel with code.** Every PR-worthy change includes tests. No exceptions.
5. **Document decisions.** Any technology choice, architectural change, or non-obvious pattern must have a brief comment or ADR entry in `docs/decisions.md` explaining _why_.
6. **Read docs before building.** Before implementing multi-city features, read `docs/seed-strategy.md`. Before adding logging/error handling, read `docs/error-monitoring.md`. Before making tech choices, read `docs/decisions.md` to check for existing ADRs.
