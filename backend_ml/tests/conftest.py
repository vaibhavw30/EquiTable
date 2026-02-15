"""
Shared test fixtures for EquiTable backend tests.

Provides:
- test_db: A clean MongoDB Atlas test database (dropped after each test)
- client: An async httpx test client wired to the FastAPI app with test DB
- sample_pantry: A valid pantry document for insertion into test DB
"""

import os

import certifi
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

import database

# Load .env so MONGO_URI is available
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

MONGO_URI = os.getenv("MONGO_URI")
TEST_DB_NAME = "equitable_test"


@pytest_asyncio.fixture
async def test_db():
    """Create a test database on Atlas that gets cleaned up after each test."""
    mongo_client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
    db = mongo_client[TEST_DB_NAME]

    # Ensure 2dsphere index exists (required for $near queries)
    await db["pantries"].create_index(
        [("location", "2dsphere")],
        name="location_2dsphere",
        sparse=True,
    )
    # City/state compound index
    await db["pantries"].create_index(
        [("city", 1), ("state", 1)],
        name="city_state",
    )
    # Unique sparse index on source_url
    await db["pantries"].create_index(
        [("source_url", 1)],
        name="source_url_unique",
        unique=True,
        sparse=True,
    )

    yield db

    # Clean up: drop the test database after each test
    await mongo_client.drop_database(TEST_DB_NAME)
    mongo_client.close()


@pytest_asyncio.fixture
async def client(test_db):
    """Async test client with test DB injected.

    Directly swaps the database module global so all route handlers
    that call get_collection() read from the test database.
    Uses the real app but skips the production lifespan by importing
    it after setting database.db.
    """
    # Swap database.db to point at test DB
    original_db = database.db
    database.db = test_db

    from main import app

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    # Restore original
    database.db = original_db


@pytest.fixture
def sample_pantry():
    """A valid pantry document matching the current Pantry model."""
    return {
        "name": "Test Community Pantry",
        "address": "123 Test St, Atlanta, GA 30301",
        "lat": 33.749,
        "lng": -84.388,
        "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
        "hours_notes": "Mon-Fri 9am-5pm",
        "eligibility_rules": ["Open to all"],
        "inventory_status": "Medium",
        "status": "OPEN",
        "hours_today": "9am-5pm",
        "is_id_required": False,
        "residency_req": None,
        "special_notes": None,
        "confidence": 8,
        "city": "Atlanta",
        "state": "GA",
        "source_url": "https://example.com/pantry",
        "last_updated": "2025-01-01T00:00:00Z",
    }
