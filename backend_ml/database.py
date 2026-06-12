"""
Database connection module for MongoDB Atlas
"""

import logging
import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

logger = logging.getLogger("equitable")

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "equitable")

client: AsyncIOMotorClient = None
db = None


def _mongo_client_kwargs() -> dict:
    """Apply TLS only for Atlas/SRV URIs.

    Atlas (mongodb+srv://) requires TLS with a CA bundle. A local/dev MongoDB
    (plain mongodb://) speaks plaintext, so passing tlsCAFile there forces a
    TLS handshake the server can't satisfy. Gate on the URI shape so the app
    runs against both Atlas and a local container. Mirrors tests/conftest.py.
    """
    uri = (MONGO_URI or "").lower()
    if "mongodb+srv" in uri or "mongodb.net" in uri or "tls=true" in uri or "ssl=true" in uri:
        return {"tlsCAFile": certifi.where()}
    return {}


async def connect_to_mongo():
    """Create database connection on startup"""
    global client, db

    if not MONGO_URI:
        raise ValueError("MONGO_URI environment variable is not set")

    client = AsyncIOMotorClient(MONGO_URI, **_mongo_client_kwargs())
    db = client[DATABASE_NAME]

    # Verify connection by pinging the server
    await client.admin.command("ping")
    logger.info("Connected to MongoDB Atlas", extra={"event": "db_connected", "database": DATABASE_NAME})

    # Create 2dsphere index on location field for geospatial queries
    await db["pantries"].create_index(
        [("location", "2dsphere")],
        name="location_2dsphere",
        sparse=True,
    )
    logger.info("Ensured 2dsphere index", extra={"event": "db_index_created", "collection": "pantries", "index": "location_2dsphere"})

    # Compound index for city/state filtering
    await db["pantries"].create_index(
        [("city", 1), ("state", 1)],
        name="city_state",
    )
    logger.info("Ensured city_state index", extra={"event": "db_index_created", "collection": "pantries", "index": "city_state"})

    # Unique sparse index on source_url for upsert logic
    await db["pantries"].create_index(
        [("source_url", 1)],
        name="source_url_unique",
        unique=True,
        sparse=True,
    )
    logger.info("Ensured source_url unique index", extra={"event": "db_index_created", "collection": "pantries", "index": "source_url_unique"})

    # TTL index on discovery_cache — auto-expire after 7 days
    await db["discovery_cache"].create_index(
        [("created_at", 1)],
        name="discovery_cache_ttl",
        expireAfterSeconds=7 * 24 * 3600,
    )
    logger.info("Ensured discovery_cache TTL index", extra={"event": "db_index_created", "collection": "discovery_cache", "index": "discovery_cache_ttl"})

    # Unique index on source_metrics.source_url
    await db["source_metrics"].create_index(
        [("source_url", 1)], name="source_metrics_url_unique", unique=True,
    )
    logger.info("Ensured source_metrics unique index", extra={"event": "db_index_created", "collection": "source_metrics", "index": "source_metrics_url_unique"})


async def close_mongo_connection():
    """Close database connection on shutdown"""
    global client

    if client:
        client.close()
        logger.info("Closed MongoDB connection", extra={"event": "db_disconnected"})


def get_database():
    """Get the database instance"""
    return db


def get_collection(collection_name: str):
    """Get a specific collection from the database"""
    return db[collection_name]
