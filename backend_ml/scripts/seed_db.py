"""
Database seeding script for EquiTable
Inserts dummy pantry data for testing

Usage: python -m scripts.seed_db
"""

import asyncio
import os
import sys
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import certifi
from models.pantry import PantryCreate, InventoryStatus, PantryStatus, make_geojson_point

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "equitable")

# Realistic Atlanta food pantries with actual coordinates
DUMMY_PANTRIES = [
    PantryCreate(
        name="Atlanta Community Food Bank",
        address="732 Joseph E Lowery Blvd NW, Atlanta, GA 30318",
        lat=33.7701,
        lng=-84.4324,
        location=make_geojson_point(33.7701, -84.4324),
        hours_notes="Mon-Fri 8am-4pm",
        eligibility_rules=[
            "No ID Required",
            "Open to all Atlanta residents",
            "One visit per household per week"
        ],
        inventory_status=InventoryStatus.HIGH,
        status=PantryStatus.OPEN,
        hours_today="8am-4pm",
        is_id_required=False,
        residency_req="Atlanta residents",
        special_notes=None,
        confidence=9,
        source_url="https://acfb.org",
        last_updated=datetime.now(timezone.utc),
    ),
    PantryCreate(
        name="Midtown Assistance Center",
        address="30 Porter Pl NE, Atlanta, GA 30308",
        lat=33.7784,
        lng=-84.3785,
        location=make_geojson_point(33.7784, -84.3785),
        hours_notes="Tue-Thu 10am-2pm",
        eligibility_rules=[
            "Fulton County Residents Only",
            "Photo ID Required",
            "Proof of Address Required"
        ],
        inventory_status=InventoryStatus.MEDIUM,
        status=PantryStatus.OPEN,
        hours_today="10am-2pm",
        is_id_required=True,
        residency_req="Fulton County residents",
        special_notes=None,
        confidence=8,
        source_url="https://midtownassistancecenter.org",
        last_updated=datetime.now(timezone.utc),
    ),
    PantryCreate(
        name="Hosea Helps",
        address="1580 Peachtree St NW, Atlanta, GA 30309",
        lat=33.7901,
        lng=-84.3856,
        location=make_geojson_point(33.7901, -84.3856),
        hours_notes="Mon, Wed, Fri 9am-1pm",
        eligibility_rules=[
            "No ID Required",
            "First Come First Served",
            "Seniors Priority (65+)"
        ],
        inventory_status=InventoryStatus.LOW,
        status=PantryStatus.WAITLIST,
        hours_today="9am-1pm",
        is_id_required=False,
        residency_req=None,
        special_notes="High demand - arrive early. Seniors served first.",
        confidence=7,
        source_url="https://hoseahelps.org",
        last_updated=datetime.now(timezone.utc),
    ),
]


async def seed_database():
    """Wipe the pantries collection and insert dummy data"""
    if not MONGO_URI:
        print("ERROR: MONGO_URI environment variable is not set")
        sys.exit(1)

    print(f"Connecting to MongoDB Atlas...")
    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client[DATABASE_NAME]

    try:
        # Verify connection
        await client.admin.command("ping")
        print(f"Connected to database: {DATABASE_NAME}")

        # Get the pantries collection
        pantries_collection = db["pantries"]

        # Wipe existing data
        result = await pantries_collection.delete_many({})
        print(f"Cleared {result.deleted_count} existing pantries")

        # Insert dummy pantries
        pantry_dicts = [pantry.model_dump() for pantry in DUMMY_PANTRIES]
        result = await pantries_collection.insert_many(pantry_dicts)

        print(f"Successfully inserted {len(result.inserted_ids)} pantries:")
        for pantry in DUMMY_PANTRIES:
            print(f"  - {pantry.name} (Inventory: {pantry.inventory_status.value})")

        # Create 2dsphere index
        await pantries_collection.create_index(
            [("location", "2dsphere")],
            name="location_2dsphere",
            sparse=True,
        )
        print("Created 2dsphere index on location")

        # Verify insertion
        count = await pantries_collection.count_documents({})
        print(f"\nTotal pantries in database: {count}")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        client.close()
        print("\nDatabase connection closed")


if __name__ == "__main__":
    print("=" * 50)
    print("EquiTable Database Seeding Script")
    print("=" * 50)
    asyncio.run(seed_database())
