# CLAUDE.md

## Project

EquiTable — AI-powered food pantry discovery platform. Scrapes pantry websites, extracts structured data via Gemini LLM, displays on interactive Google Map.

## Quick Context

- **Frontend**: React 19 + Vite 7, Tailwind CSS 4, Framer Motion, Google Maps API → deployed on Vercel
- **Backend**: FastAPI (Python 3.10+), Motor (async MongoDB), Gemini 2.0 Flash, Firecrawl → deployed on Render
- **Database**: MongoDB Atlas with 2dsphere geospatial indexing

## Agent System

This project uses subagents for structured development. Read these before working:

- `AGENTS.md` — Full project context, tech stack, DB schema, API contracts, conventions, smoke tests
- `agents/planner-tech-advisor.md` — Feature specs + tech evaluation (invoke FIRST for any new feature)
- `agents/backend.md` — FastAPI patterns, DB patterns, testing infrastructure
- `agents/scraping-quality.md` — Scraping pipeline, LLM extraction, fixture-based testing
- `agents/frontend-ui.md` — Components, animations, design system, accessibility
- `agents/frontend-data.md` — API services, hooks, state management, routing

## Key Rules

1. **Planner first.** No feature work without a spec from the planner agent.
2. **Tests travel with code.** Every change includes tests. No exceptions.
3. **Smoke tests must always pass** before any merge:
   - Health check returns 200
   - `/pantries` returns valid list
   - `/pantries/nearby` returns geospatially correct results
   - Frontend renders landing page without errors
   - Frontend renders map page and loads markers
   - Scraping pipeline produces valid output for test fixture URLs
   - Confidence scores are 1-10 and non-null for scraped pantries
4. **API contracts are sacred.** Backend response shape changes require spec update first.
5. **Boundaries matter.** Backend agent doesn't touch frontend. Frontend agents don't touch backend. Scraping Quality agent owns `scraper.py`, `extractor.py`, `validator.py`.

## Commands

```bash
# Backend
cd backend_ml
source venv/bin/activate
uvicorn main:app --reload --host 127.0.0.1 --port 8000
python -m pytest tests/ -v                    # all tests
python -m pytest tests/test_smoke.py -v       # smoke tests only

# Frontend
cd frontend
npm run dev
npm run test                                   # all tests
npm run test -- --grep "smoke"                # smoke tests only
npm run build                                  # production build
```

## Environment Variables

```bash
# Backend (.env)
GEMINI_API_KEY=
FIRECRAWL_API_KEY=
MONGODB_URI=
JWT_SECRET=          # planned

# Frontend (.env)
VITE_API_URL=http://127.0.0.1:8000
VITE_GOOGLE_MAPS_KEY=
```

## Documentation

Read these before making decisions or implementing features:

- `docs/decisions.md` — Architecture Decision Records. Log of all major tech choices with rationale. **Add a new ADR here whenever you make a significant technology or architecture decision.**
- `docs/seed-strategy.md` — Multi-city expansion plan. Which cities to seed, how to source URLs, seed script design, freshness policy. **Read before any work on multi-city or discovery features.**
- `docs/error-monitoring.md` — Logging and error handling patterns. Structured JSON logging for backend, React ErrorBoundary, API error surfacing. **Follow these patterns when adding logging or error handling.**

## Current Phase

Phase 2: Scraping Quality Overhaul → then Phase 1: Multi-City Expansion. See `agents/planner-tech-advisor.md` for full roadmap.
