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


async def connect_to_mongo():
    """Create database connection on startup"""
    global client, db

    if not MONGO_URI:
        raise ValueError("MONGO_URI environment variable is not set")

    client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
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
