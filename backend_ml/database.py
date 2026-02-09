"""
Database connection module for MongoDB Atlas
"""

import os
import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

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
    print(f"Connected to MongoDB Atlas - Database: {DATABASE_NAME}")

    # Create 2dsphere index on location field for geospatial queries
    await db["pantries"].create_index(
        [("location", "2dsphere")],
        name="location_2dsphere",
        sparse=True,
    )
    print("Ensured 2dsphere index on pantries.location")


async def close_mongo_connection():
    """Close database connection on shutdown"""
    global client

    if client:
        client.close()
        print("Closed MongoDB connection")


def get_database():
    """Get the database instance"""
    return db


def get_collection(collection_name: str):
    """Get a specific collection from the database"""
    return db[collection_name]
