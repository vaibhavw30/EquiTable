"""
Multi-City Seed Script - Seeds pantry data for Tier 1 cities using
the IngestionPipeline (Crawl4AI -> Gemini -> Validator).

Upserts by source_url to avoid duplicates. Safe to re-run.

Usage:
    cd backend_ml
    python -m scripts.seed_cities                    # Seed all cities
    python -m scripts.seed_cities --city "Atlanta"   # Seed one city
    python -m scripts.seed_cities --tier 1           # Seed Tier 1 only
    python -m scripts.seed_cities --dry-run          # Preview without scraping
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from models.pantry import PantryCreate, make_geojson_point
from services.scraper import get_scraper_service
from services.llm import get_llm_service
from services.ingestion_pipeline import IngestionPipeline, IngestionError

load_dotenv()

logger = logging.getLogger("equitable.seed")

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "equitable")
SEED_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "seed_urls.json",
)
FRESHNESS_HOURS = 24


def load_seed_data() -> list[dict]:
    """Load seed URL data from JSON file."""
    with open(SEED_DATA_PATH, "r") as f:
        data = json.load(f)
    return data["cities"]


def filter_cities(cities: list[dict], city_name: str | None, tier: int | None) -> list[dict]:
    """Filter cities by name or tier."""
    if city_name:
        cities = [c for c in cities if c["city"].lower() == city_name.lower()]
    if tier is not None:
        cities = [c for c in cities if c.get("tier") == tier]
    return cities


async def seed(args):
    """Main seeding logic."""
    cities = load_seed_data()
    cities = filter_cities(cities, args.city, args.tier)

    if not cities:
        print("No cities match the given filters.")
        return

    print("=" * 60)
    print("EquiTable - Multi-City Seed Script")
    print("=" * 60)
    print(f"Cities to seed: {', '.join(c['city'] for c in cities)}")
    print(f"Dry run: {args.dry_run}")
    print()

    if args.dry_run:
        for city_data in cities:
            print(f"\n[{city_data['city']}, {city_data['state']}] — {len(city_data['pantries'])} pantries")
            for p in city_data["pantries"]:
                print(f"  - {p['name']}: {p['url']}")
        print(f"\nTotal: {sum(len(c['pantries']) for c in cities)} pantries across {len(cities)} cities")
        return

    # Connect to MongoDB
    mongo_client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = mongo_client[DATABASE_NAME]
    await mongo_client.admin.command("ping")
    print("Connected to MongoDB Atlas\n")

    pantries_collection = db["pantries"]

    # Ensure indexes
    await pantries_collection.create_index(
        [("location", "2dsphere")], name="location_2dsphere", sparse=True,
    )
    await pantries_collection.create_index(
        [("city", 1), ("state", 1)], name="city_state",
    )
    await pantries_collection.create_index(
        [("source_url", 1)], name="source_url_unique", unique=True, sparse=True,
    )

    # Init pipeline
    scraper = get_scraper_service()
    llm = get_llm_service()
    pipeline = IngestionPipeline(scraper=scraper, extractor=llm.extractor)

    total_seeded = 0
    total_skipped = 0
    total_failed = 0
    failures = []

    for city_data in cities:
        city_name = city_data["city"]
        state = city_data["state"]
        city_pantries = city_data["pantries"]
        city_seeded = 0
        city_skipped = 0

        print(f"\n{'─' * 50}")
        print(f"[{city_name}, {state}] — {len(city_pantries)} pantries")
        print(f"{'─' * 50}")

        for i, p in enumerate(city_pantries, 1):
            url = p["url"]
            name = p["name"]
            print(f"  [{i}/{len(city_pantries)}] {name}")

            # Check freshness: skip if < 24h old
            existing = await pantries_collection.find_one({"source_url": url})
            if existing and existing.get("last_updated"):
                last_updated = existing["last_updated"]
                if isinstance(last_updated, str):
                    last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
                if not last_updated.tzinfo:
                    last_updated = last_updated.replace(tzinfo=timezone.utc)
                age = datetime.now(timezone.utc) - last_updated
                if age < timedelta(hours=FRESHNESS_HOURS):
                    print(f"    SKIP — updated {age.total_seconds() / 3600:.1f}h ago")
                    city_skipped += 1
                    total_skipped += 1
                    continue

            # Run ingestion pipeline
            try:
                update_data = await pipeline.ingest(url)
            except IngestionError as e:
                print(f"    FAILED — {e.stage}: {e.reason}")
                failures.append({"city": city_name, "name": name, "url": url, "error": str(e)})
                total_failed += 1
                # Still insert with defaults so we have the pantry in the map
                doc = PantryCreate(
                    name=name,
                    address=p["address"],
                    lat=p["lat"],
                    lng=p["lng"],
                    location=make_geojson_point(p["lat"], p["lng"]),
                    hours_notes="Not available - website could not be reached",
                    city=city_name,
                    state=state,
                    source_url=url,
                    last_updated=datetime.now(timezone.utc),
                ).model_dump()

                await pantries_collection.update_one(
                    {"source_url": url},
                    {"$set": doc},
                    upsert=True,
                )
                city_seeded += 1
                total_seeded += 1
                time.sleep(1)
                continue

            # Build the full document via upsert
            doc = PantryCreate(
                name=name,
                address=p["address"],
                lat=p["lat"],
                lng=p["lng"],
                location=make_geojson_point(p["lat"], p["lng"]),
                hours_notes=update_data.hours_notes,
                eligibility_rules=update_data.eligibility_rules,
                status=update_data.status,
                hours_today=update_data.hours_today,
                is_id_required=update_data.is_id_required,
                residency_req=update_data.residency_req,
                special_notes=update_data.special_notes,
                confidence=update_data.confidence,
                city=city_name,
                state=state,
                source_url=url,
                last_updated=datetime.now(timezone.utc),
            ).model_dump()

            await pantries_collection.update_one(
                {"source_url": url},
                {"$set": doc},
                upsert=True,
            )

            city_seeded += 1
            total_seeded += 1
            print(f"    OK — confidence={update_data.confidence}, status={update_data.status}")
            time.sleep(2)  # Rate limit

        print(f"  [{city_name}] Seeded {city_seeded}, skipped {city_skipped}")

    # Summary
    total = await pantries_collection.count_documents({})
    print()
    print("=" * 60)
    print(f"DONE — {total} total pantries in database")
    print(f"  Seeded: {total_seeded}")
    print(f"  Skipped (fresh): {total_skipped}")
    print(f"  Failed: {total_failed}")
    if failures:
        print("  Failures:")
        for f in failures:
            print(f"    - [{f['city']}] {f['name']}: {f['error']}")
    print("=" * 60)

    mongo_client.close()


def main():
    parser = argparse.ArgumentParser(description="Seed EquiTable with multi-city pantry data")
    parser.add_argument("--city", type=str, help="Seed a specific city (e.g. 'Atlanta')")
    parser.add_argument("--tier", type=int, help="Seed a specific tier (e.g. 1)")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be seeded")
    args = parser.parse_args()
    asyncio.run(seed(args))


if __name__ == "__main__":
    main()
