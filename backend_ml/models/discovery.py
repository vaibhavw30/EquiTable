"""
Discovery models - Request/response schemas for live pantry discovery.

Used by the discovery service and API routes. Does not define route
handlers (that's the backend agent's domain).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class DiscoveryStatus(str, Enum):
    """Status of a discovery job."""
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class DiscoveryRequest(BaseModel):
    """Request body for starting a discovery job."""
    query: str = Field(..., description="Human-readable location (e.g. 'Denver, CO')")
    lat: float = Field(..., ge=-90, le=90, description="Latitude of search center")
    lng: float = Field(..., ge=-180, le=180, description="Longitude of search center")
    radius_meters: int = Field(
        default=8000,
        ge=500,
        le=50000,
        description="Search radius in meters (default ~5 miles, max 50km)",
    )


class DiscoveryResponse(BaseModel):
    """Response from starting a discovery job."""
    job_id: str
    status: DiscoveryStatus = DiscoveryStatus.RUNNING
    stream_url: str
    existing_pantries: int = Field(
        default=0,
        description="Fresh pantries already in DB for this area",
    )


class DiscoveryJobStatus(BaseModel):
    """Full status of a discovery job (for polling endpoint)."""
    job_id: str
    status: DiscoveryStatus
    query: str
    urls_found: int = 0
    urls_processed: int = 0
    urls_succeeded: int = 0
    urls_failed: int = 0
    urls_skipped: int = 0
    pantry_ids: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class PlaceResult(BaseModel):
    """A food pantry/bank found via Google Places API."""
    name: str
    address: str
    lat: float
    lng: float
    website_url: Optional[str] = None
    place_id: str = ""
