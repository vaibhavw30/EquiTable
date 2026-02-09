"""
EquiTable API - Food Rescue Agent Backend
"""

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
from services.llm import get_llm_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events"""
    # Startup
    try:
        await connect_to_mongo()
        print("Database connection established")
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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


@app.get("/pantries/nearby", response_model=list[Pantry])
async def get_nearby_pantries(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    max_distance: int = Query(16093, description="Max distance in meters (default ~10 miles)"),
    status: Optional[PantryStatus] = Query(None, description="Filter by operational status"),
):
    """
    Find pantries near a given location using MongoDB $near geospatial query.
    Results are sorted by distance (closest first).
    """
    try:
        pantries_collection = get_collection("pantries")

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
        async for document in pantries_collection.find(query):
            pantries.append(Pantry(**document))

        return pantries
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/pantries", response_model=list[Pantry])
async def get_pantries():
    """
    Retrieve all pantries from the database.
    Returns a list of Pantry objects with _id serialized as string.
    """
    try:
        pantries_collection = get_collection("pantries")
        pantries = []

        cursor = pantries_collection.find({})
        async for document in cursor:
            pantries.append(Pantry(**document))

        return pantries
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.post("/pantries/{pantry_id}/ingest")
async def ingest_pantry(pantry_id: str, request: IngestRequest):
    """
    Full ingestion pipeline for a single pantry:
    1. Validate pantry exists
    2. Scrape the provided URL via Firecrawl
    3. Extract structured data via Azure OpenAI
    4. Merge extracted fields into the pantry document
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

    # 2. Scrape the URL
    scraper = get_scraper_service()
    raw_text = scraper.scrape_url(request.url)
    if not raw_text:
        raise HTTPException(status_code=502, detail=f"Failed to scrape {request.url}")

    # 3. Extract structured data via LLM
    llm = get_llm_service()
    update_data = await llm.extract_data(raw_text)
    if not update_data:
        raise HTTPException(status_code=502, detail="LLM failed to extract structured data")

    # 4. Merge into the document
    update_fields = update_data.model_dump()
    update_fields["source_url"] = request.url
    update_fields["last_updated"] = datetime.now(timezone.utc)

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
