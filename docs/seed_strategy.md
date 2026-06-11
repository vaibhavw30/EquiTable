# Multi-City Seed Data Strategy

This document defines which cities get pre-seeded pantry data, how seed URLs are sourced, and how the seed script works.

## Target Cities (Phase 1)

Seed ~5 verified pantries per city. Prioritize cities with high food insecurity rates and good pantry website coverage.

### Tier 1 — Launch Cities (seed first)

| City          | State | Reason                                | Seed Count        |
| ------------- | ----- | ------------------------------------- | ----------------- |
| Atlanta       | GA    | Existing data, home base              | 15 (already done) |
| New York City | NY    | Largest metro, high need              | 5                 |
| Los Angeles   | CA    | Second largest metro                  | 5                 |
| Chicago       | IL    | Major metro, high food desert density | 5                 |
| Houston       | TX    | Large metro, spread-out geography     | 5                 |

### Tier 2 — Expansion Cities (seed after Tier 1 stable)

| City          | State | Seed Count |
| ------------- | ----- | ---------- |
| Philadelphia  | PA    | 5          |
| Phoenix       | AZ    | 5          |
| Dallas        | TX    | 5          |
| Detroit       | MI    | 5          |
| Miami         | FL    | 5          |
| Washington DC | DC    | 5          |
| Denver        | CO    | 5          |
| Seattle       | WA    | 5          |
| Minneapolis   | MN    | 5          |
| Baltimore     | MD    | 5          |

### Tier 3 — On-Demand Only

All other cities rely on live async discovery (no pre-seeded data). When a user pans the map to an unseeded city, the discover endpoint triggers live scraping.

## How to Source Seed URLs

For each city, find 5 pantry URLs using this process:

1. **Search**: `"food pantry" OR "food bank" [city name]` on Google
2. **Prioritize**: Sites with dedicated pantry pages (not just directory listings)
3. **Verify**: Each URL is scrapeable (not behind login, not pure PDF, loads in browser)
4. **Diversify**: Mix of large food banks, small church pantries, community orgs — don't just pick the top 5 Google results
5. **Record**: Add URL + basic metadata to `backend_ml/data/seed_urls.json`

### Seed URL Format

```json
// backend_ml/data/seed_urls.json
{
  "cities": [
    {
      "city": "Atlanta",
      "state": "GA",
      "center": { "lat": 33.749, "lng": -84.388 },
      "pantries": [
        {
          "name": "Atlanta Community Food Bank",
          "url": "https://www.acfb.org/",
          "address": "732 Joseph E Lowery Blvd NW, Atlanta, GA 30318",
          "lat": 33.7726,
          "lng": -84.4225,
          "notes": "Large regional food bank, good website"
        }
      ]
    },
    {
      "city": "New York City",
      "state": "NY",
      "center": { "lat": 40.7128, "lng": -74.006 },
      "pantries": [
        {
          "name": "City Harvest",
          "url": "https://www.cityharvest.org/",
          "address": "6 East 32nd Street, New York, NY 10016",
          "lat": 40.7468,
          "lng": -73.9837,
          "notes": "Major NYC food rescue org"
        }
      ]
    }
  ]
}
```

## Seed Script Design

```bash
# Usage
cd backend_ml
python scripts/seed_cities.py                    # Seed all cities
python scripts/seed_cities.py --city "Atlanta"   # Seed one city
python scripts/seed_cities.py --tier 1           # Seed Tier 1 cities only
python scripts/seed_cities.py --dry-run          # Show what would be scraped without doing it
```

### Script Logic

```
For each city in seed_urls.json (filtered by args):
  For each pantry URL:
    1. Check if pantry already exists in DB (by source_url)
       → If exists and last_updated < 24 hours ago, skip
       → If exists and stale, re-scrape
       → If not exists, scrape fresh

    2. Scrape URL via scraping pipeline
       → On success: extract structured data, validate, store
       → On failure: log error, continue to next URL

    3. Log results:
       → "[city] Seeded 4/5 pantries (1 failed: timeout on URL X)"

  After all pantries in city:
    4. Verify geospatial index exists for new entries
    5. Log city summary
```

### Error Handling

- Individual pantry failures don't stop the batch
- Retry once with exponential backoff on timeout
- Log all failures to `backend_ml/logs/seed_errors.json` with URL, error, timestamp
- After completion, print summary: `X/Y pantries seeded across Z cities, N failures`

### Scheduling

For now, seeding is manual (run script when adding new cities). Future: could run as a weekly cron job on Render to refresh stale data, but that's Phase 3+.

## Freshness Policy

| Data Age          | Action                                                             |
| ----------------- | ------------------------------------------------------------------ |
| < 24 hours        | Serve from cache, no re-scrape                                     |
| 24 hours - 7 days | Serve from cache, background re-scrape if user visits              |
| > 7 days          | Flag as potentially stale in UI (amber indicator), queue re-scrape |
| > 30 days         | Mark as unverified, lower confidence by 2 points in UI             |

## Live Discovery (complements seeding)

When a user pans the map to an area with no seeded data:

1. Frontend detects no pantries in viewport bounds
2. Sends `POST /pantries/discover` with bounds
3. Backend searches for food pantries in that area (via Google Places API or similar)
4. For each found pantry, checks if we already have it
5. Scrapes unknown pantries asynchronously
6. Frontend polls for results, shows them progressively

**Key difference from seeding**: Discovery is reactive (user-triggered) and uses location-based search to find pantry URLs, while seeding is proactive (developer-curated URLs). Discovery results become permanent — once a pantry is scraped, it's in the DB for all future users.
