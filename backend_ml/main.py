"""
EquiTable API - Food Rescue Agent Backend
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import connect_to_mongo, close_mongo_connection, get_collection
from models.pantry import Pantry, PantryStatus
from services.scraper import get_scraper_service
from services.extractor import ExtractorService
from services.ingestion_pipeline import IngestionPipeline, IngestionError
from services.llm import get_llm_service

logger = logging.getLogger("equitable")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events"""
    # Startup
    try:
        await connect_to_mongo()
        logger.info("Database connection established", extra={"event": "startup_complete"})
    except Exception as e:
        logger.error("Failed to connect to MongoDB", extra={"event": "startup_failed", "error": str(e)})
        raise

    yield

    # Shutdown
    await close_mongo_connection()


app = FastAPI(
    title="EquiTable API",
    description="AI-powered food rescue agent",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware configuration
# Use regex to match all Vercel preview/production URLs + localhost for dev
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.vercel\.app|http://localhost:\d+|http://127\.0\.0\.1:\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {"message": "EquiTable API is running"}


@app.get("/api/test")
async def test_connection():
    """Test endpoint for frontend connectivity check"""
    return {"status": "connected", "agent": "EquiTable v1"}


class IngestRequest(BaseModel):
    """Request body for the ingest endpoint."""
    url: str
    city: Optional[str] = None
    state: Optional[str] = None


# Static city center coordinates for the /cities endpoint
CITY_CENTERS = {
    ("Atlanta", "GA"): {"lat": 33.749, "lng": -84.388},
    ("New York City", "NY"): {"lat": 40.7128, "lng": -74.006},
    ("Los Angeles", "CA"): {"lat": 34.0522, "lng": -118.2437},
    ("Chicago", "IL"): {"lat": 41.8781, "lng": -87.6298},
    ("Houston", "TX"): {"lat": 29.7604, "lng": -95.3698},
    ("Oakland", "CA"): {"lat": 37.8044, "lng": -122.2712},
    ("San Francisco", "CA"): {"lat": 37.7749, "lng": -122.4194},
    ("San Diego", "CA"): {"lat": 32.7157, "lng": -117.1611},
}


MAX_NEARBY_DISTANCE = 5_000_000  # ~3100 miles server-side cap


@app.get("/pantries/nearby", response_model=list[Pantry])
async def get_nearby_pantries(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    max_distance: int = Query(16093, description="Max distance in meters (default ~10 miles)"),
    limit: int = Query(200, ge=1, le=500, description="Max results to return"),
    status: Optional[PantryStatus] = Query(None, description="Filter by operational status"),
):
    """
    Find pantries near a given location using MongoDB $near geospatial query.
    Results are sorted by distance (closest first).
    """
    try:
        pantries_collection = get_collection("pantries")
        max_distance = min(max_distance, MAX_NEARBY_DISTANCE)

        query = {
            "location": {
                "$near": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [lng, lat],
                    },
                    "$maxDistance": max_distance,
                }
            }
        }

        if status:
            query["status"] = status.value

        pantries = []
        async for document in pantries_collection.find(query).limit(limit):
            pantries.append(Pantry(**document))

        return pantries
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/pantries", response_model=list[Pantry])
async def get_pantries(
    city: Optional[str] = Query(None, description="Filter by city name (case-insensitive)"),
    state: Optional[str] = Query(None, description="Filter by state abbreviation (case-insensitive)"),
):
    """
    Retrieve pantries from the database, optionally filtered by city/state.
    No params returns all pantries (backward-compatible).
    """
    try:
        pantries_collection = get_collection("pantries")
        query = {}

        if city:
            query["city"] = {"$regex": f"^{city}$", "$options": "i"}
        if state:
            query["state"] = {"$regex": f"^{state}$", "$options": "i"}

        pantries = []
        cursor = pantries_collection.find(query)
        async for document in cursor:
            pantries.append(Pantry(**document))

        return pantries
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/cities")
async def get_cities():
    """
    Returns a list of cities with pantry counts and map center coordinates.
    Uses MongoDB aggregation to group by city/state.
    """
    try:
        pantries_collection = get_collection("pantries")

        pipeline = [
            {"$match": {"city": {"$ne": None}}},
            {"$group": {"_id": {"city": "$city", "state": "$state"}, "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]

        cities = []
        async for doc in pantries_collection.aggregate(pipeline):
            city = doc["_id"]["city"]
            state = doc["_id"]["state"]
            center = CITY_CENTERS.get((city, state), {"lat": 0, "lng": 0})
            cities.append({
                "city": city,
                "state": state,
                "count": doc["count"],
                "center": center,
            })

        return cities
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.post("/pantries/{pantry_id}/ingest")
async def ingest_pantry(pantry_id: str, request: IngestRequest):
    """
    Full ingestion pipeline for a single pantry:
    1. Validate pantry exists
    2. Scrape → Extract → Validate via IngestionPipeline
    3. Merge extracted fields into the pantry document
    """
    pantries_collection = get_collection("pantries")

    # 1. Validate pantry exists
    try:
        oid = ObjectId(pantry_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pantry ID format")

    existing = await pantries_collection.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Pantry not found")

    # 2. Run ingestion pipeline: scrape → extract → validate
    try:
        llm = get_llm_service()
        pipeline = IngestionPipeline(
            scraper=get_scraper_service(),
            extractor=llm.extractor,
        )
        update_data = await pipeline.ingest(request.url)
    except IngestionError as e:
        logger.warning(
            "Ingestion failed",
            extra={"event": "ingestion_endpoint_failed", "stage": e.stage, "url": e.url, "error": e.reason},
        )
        status_code = 502 if e.stage in ("scrape", "extract") else 422
        raise HTTPException(status_code=status_code, detail=str(e))

    # 3. Merge into the document
    update_fields = update_data.model_dump()
    update_fields["source_url"] = request.url
    update_fields["last_updated"] = datetime.now(timezone.utc)
    if request.city:
        update_fields["city"] = request.city
    if request.state:
        update_fields["state"] = request.state

    await pantries_collection.update_one(
        {"_id": oid},
        {"$set": update_fields},
    )

    # Return the updated document
    updated = await pantries_collection.find_one({"_id": oid})
    return Pantry(**updated)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
