"""
Bulk Ingestion Script - Scrape real Atlanta food pantry websites,
extract structured data via Azure OpenAI, and store in MongoDB.

Caches scraped content to .scrape_cache.json so re-runs only cost
LLM calls, not Firecrawl credits.

Usage: python -m scripts.ingest_real_pantries
       python -m scripts.ingest_real_pantries --no-cache   # force re-scrape
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

from models.pantry import (
    PantryCreate, InventoryStatus, PantryStatus, make_geojson_point,
)
from services.scraper import ScraperService
from services.llm import LLMService

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "equitable")

CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".scrape_cache.json"
)

# ── 15 Real Atlanta Food Pantries ──────────────────────────────────────
# Each entry: (name, address, lat, lng, source_url)
PANTRY_SOURCES = [
    # ── Midtown ──
    (
        "Midtown Assistance Center",
        "30 Porter Pl NE, Atlanta, GA 30308",
        33.7784, -84.3785,
        "https://midtownassistancecenter.org",
    ),
    (
        "Venable Food Market (First Presbyterian Church)",
        "1328 Peachtree St NE, Atlanta, GA 30309",
        33.7878, -84.3833,
        "https://firstpresatl.org/community-ministries",
    ),
    (
        "Lutheran Community Food Ministry (Church of the Redeemer)",
        "731 Peachtree St NE, Atlanta, GA 30308",
        33.7726, -84.3843,
        "https://redeemer.org",
    ),
    (
        "Grace House Community Fridge",
        "800 Monroe Dr NE, Atlanta, GA 30308",
        33.7818, -84.3650,
        "https://gracepeople.org",
    ),
    (
        "Klemis Kitchen (Georgia Tech)",
        "353 Ferst Dr NW, Atlanta, GA 30332",
        33.7756, -84.3963,
        "https://star.studentlife.gatech.edu/klemis-kitchen",
    ),
    (
        "Atlanta Mission (My Sister's House)",
        "921 Howell Mill Rd NW, Atlanta, GA 30318",
        33.7814, -84.4103,
        "https://atlantamission.org/my-sisters-house",
    ),
    # ── Downtown & Sweet Auburn ──
    (
        "Catholic Shrine of the Immaculate Conception (St. Francis Table)",
        "48 Martin Luther King Jr Dr SW, Atlanta, GA 30303",
        33.7537, -84.3907,
        "https://catholicshrineatlanta.org",
    ),
    (
        "St. Luke's Episcopal Church (Community Ministries)",
        "435 Peachtree St NE, Atlanta, GA 30308",
        33.7642, -84.3862,
        "https://stlukesatlanta.org",
    ),
    (
        "The Action Mission Ministry (Wheat Street Baptist Church)",
        "359 Auburn Ave NE, Atlanta, GA 30312",
        33.7561, -84.3766,
        "https://wearewheatstreet.org",
    ),
    (
        "Ebenezer Baptist Church Food Pantry",
        "407 Auburn Ave NE, Atlanta, GA 30312",
        33.7548, -84.3725,
        "https://ebenezeratl.org",
    ),
    (
        "Big Bethel AME Church",
        "220 Auburn Ave NE, Atlanta, GA 30303",
        33.7555, -84.3803,
        "https://ampleharvest.org/bethel-ame",
    ),
    (
        "Salvation Army Red Shield Services",
        "100 Edgewood Ave NE, Atlanta, GA 30303",
        33.7553, -84.3808,
        "https://salvationarmyusa.org/atlanta",
    ),
    # ── Near Downtown (O4W / Grant Park / Ponce) ──
    (
        "Foundation of Miracles",
        "Atlanta, GA 30312",
        33.7450, -84.3700,
        "https://foundationofmiracles.org",
    ),
    (
        "Intown Collaborative Ministries",
        "1017 Edgewood Ave NE, Atlanta, GA 30307",
        33.7543, -84.3540,
        "https://intowncm.org",
    ),
    (
        "Loaves & Fishes (St. John the Wonderworker)",
        "541 Atlanta Ave SE, Atlanta, GA 30315",
        33.7290, -84.3750,
        "https://saintjohnwonderworker.org/loaves",
    ),
]


def load_cache() -> dict:
    """Load cached scraped content from disk."""
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict):
    """Save scraped content cache to disk."""
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


async def main():
    use_cache = "--no-cache" not in sys.argv

    print("=" * 60)
    print("EquiTable - Bulk Real Pantry Ingestion")
    print("=" * 60)
    print(f"Pantries to process: {len(PANTRY_SOURCES)}")

    # ── Load scrape cache ──
    cache = load_cache() if use_cache else {}
    cached_count = sum(1 for _, _, _, _, url in PANTRY_SOURCES if url in cache)
    new_scrapes = len(PANTRY_SOURCES) - cached_count
    print(f"Cached scrapes: {cached_count}  |  New Firecrawl calls: {new_scrapes}\n")

    # ── Init services ──
    scraper = None
    if new_scrapes > 0:
        try:
            scraper = ScraperService()
        except ValueError as e:
            print(f"ERROR (scraper): {e}")
            sys.exit(1)

    try:
        llm = LLMService()
    except ValueError as e:
        print(f"ERROR (llm): {e}")
        sys.exit(1)

    # ── Connect to MongoDB ──
    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DATABASE_NAME]
    await client.admin.command("ping")
    print("Connected to MongoDB Atlas\n")

    pantries_collection = db["pantries"]

    # Clear existing data
    result = await pantries_collection.delete_many({})
    print(f"Cleared {result.deleted_count} existing pantries\n")

    # ── Process each pantry ──
    succeeded = 0
    failed_scrape = []
    failed_llm = []

    for i, (name, address, lat, lng, url) in enumerate(PANTRY_SOURCES, 1):
        print(f"[{i}/{len(PANTRY_SOURCES)}] {name}")
        print(f"  URL: {url}")

        # ── Scrape (or use cache) ──
        if url in cache:
            raw_text = cache[url]
            print(f"  CACHED — {len(raw_text)} chars")
        else:
            raw_text = scraper.scrape_url(url) if scraper else None
            if raw_text:
                cache[url] = raw_text
                save_cache(cache)
                print(f"  Scraped {len(raw_text)} chars")
            time.sleep(1)

        if not raw_text:
            print(f"  SCRAPE FAILED — inserting with defaults\n")
            failed_scrape.append(name)
            pantry = PantryCreate(
                name=name,
                address=address,
                lat=lat,
                lng=lng,
                location=make_geojson_point(lat, lng),
                hours_notes="Not available - website could not be reached",
                source_url=url,
                last_updated=datetime.now(timezone.utc),
            )
            await pantries_collection.insert_one(pantry.model_dump())
            succeeded += 1
            continue

        # ── Extract via LLM ──
        update_data = await llm.extract_data(raw_text)

        if not update_data:
            print(f"  LLM EXTRACTION FAILED — inserting with defaults\n")
            failed_llm.append(name)
            pantry = PantryCreate(
                name=name,
                address=address,
                lat=lat,
                lng=lng,
                location=make_geojson_point(lat, lng),
                hours_notes="Not available - extraction failed",
                source_url=url,
                last_updated=datetime.now(timezone.utc),
            )
            await pantries_collection.insert_one(pantry.model_dump())
            succeeded += 1
            continue

        # ── Build full document with REAL extracted data ──
        pantry = PantryCreate(
            name=name,
            address=address,
            lat=lat,
            lng=lng,
            location=make_geojson_point(lat, lng),
            hours_notes=update_data.hours_notes,
            eligibility_rules=update_data.eligibility_rules,
            inventory_status=InventoryStatus.MEDIUM,
            status=update_data.status,
            hours_today=update_data.hours_today,
            is_id_required=update_data.is_id_required,
            residency_req=update_data.residency_req,
            special_notes=update_data.special_notes,
            confidence=update_data.confidence,
            source_url=url,
            last_updated=datetime.now(timezone.utc),
        )

        await pantries_collection.insert_one(pantry.model_dump())
        succeeded += 1
        print(f"  status    = {update_data.status}")
        print(f"  hours     = {update_data.hours_notes}")
        print(f"  today     = {update_data.hours_today}")
        print(f"  id_req    = {update_data.is_id_required}")
        print(f"  residency = {update_data.residency_req}")
        print(f"  rules     = {update_data.eligibility_rules}")
        print(f"  notes     = {update_data.special_notes}")
        print(f"  conf      = {update_data.confidence}")
        print()

    # ── Create indexes ──
    await pantries_collection.create_index(
        [("location", "2dsphere")],
        name="location_2dsphere",
        sparse=True,
    )
    print("Created 2dsphere index")

    # ── Summary ──
    total = await pantries_collection.count_documents({})
    print()
    print("=" * 60)
    print(f"DONE — {total} pantries in database")
    print(f"  Succeeded: {succeeded}")
    if failed_scrape:
        print(f"  Scrape failures (inserted with defaults): {len(failed_scrape)}")
        for n in failed_scrape:
            print(f"    - {n}")
    if failed_llm:
        print(f"  LLM failures (inserted with defaults): {len(failed_llm)}")
        for n in failed_llm:
            print(f"    - {n}")
    print("=" * 60)

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
