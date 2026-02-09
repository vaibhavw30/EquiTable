"""
Pantry model - Represents a food rescue location
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Optional, List
from pydantic import BaseModel, Field, BeforeValidator

# Custom type for handling MongoDB ObjectId
# Converts ObjectId to string for JSON serialization
PyObjectId = Annotated[str, BeforeValidator(str)]


class InventoryStatus(str, Enum):
    """Enum representing current inventory levels at a pantry"""
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class PantryStatus(str, Enum):
    """Enum representing operational status of a pantry"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    WAITLIST = "WAITLIST"
    UNKNOWN = "UNKNOWN"


class GeoJSONPoint(BaseModel):
    """GeoJSON Point for MongoDB 2dsphere index"""
    type: str = Field(default="Point", description="GeoJSON type")
    coordinates: List[float] = Field(
        ...,
        description="[longitude, latitude] - NOTE: GeoJSON uses lng,lat order"
    )


def make_geojson_point(lat: float, lng: float) -> GeoJSONPoint:
    """Create a GeoJSON Point from lat/lng. GeoJSON order is [lng, lat]."""
    return GeoJSONPoint(type="Point", coordinates=[lng, lat])


class Pantry(BaseModel):
    """
    Pydantic model representing a food pantry/rescue location.
    Includes both static pantry info AND dynamic LLM-extracted fields.
    """
    # === Identity ===
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    name: str = Field(..., description="Name of the pantry")
    address: str = Field(..., description="Street address")

    # === Geolocation (backward-compatible flat fields) ===
    lat: float = Field(..., description="Latitude coordinate")
    lng: float = Field(..., description="Longitude coordinate")

    # === GeoJSON (for 2dsphere queries) ===
    location: Optional[GeoJSONPoint] = Field(
        default=None,
        description="GeoJSON Point for geospatial queries"
    )

    # === Static pantry info ===
    hours_notes: str = Field(..., description="Operating hours (e.g., 'Mon-Fri 9am-5pm')")
    eligibility_rules: List[str] = Field(
        default_factory=list,
        description="List of eligibility requirements"
    )
    inventory_status: InventoryStatus = Field(
        default=InventoryStatus.MEDIUM,
        description="Current inventory level (High, Medium, Low)"
    )

    # === LLM-extracted fields (from PantryUpdate) ===
    status: PantryStatus = Field(
        default=PantryStatus.UNKNOWN,
        description="Current operational status (OPEN/CLOSED/WAITLIST/UNKNOWN)"
    )
    hours_today: Optional[str] = Field(
        default=None,
        description="Normalized hours for today, e.g. '9am-5pm' or 'Unknown'"
    )
    is_id_required: Optional[bool] = Field(
        default=None,
        description="True if text mentions ID, License, or documentation"
    )
    residency_req: Optional[str] = Field(
        default=None,
        description="Specific county or zip code requirements, if any"
    )
    special_notes: Optional[str] = Field(
        default=None,
        description="Temporary closures or urgent alerts"
    )
    confidence: Optional[int] = Field(
        default=None,
        description="1-10 score of how clear the extracted info was"
    )

    # === Metadata ===
    source_url: Optional[str] = Field(
        default=None,
        description="URL of the pantry's website that was scraped"
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp"
    )

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "use_enum_values": True,
        "json_schema_extra": {
            "example": {
                "name": "Atlanta Community Food Bank",
                "address": "732 Joseph E Lowery Blvd NW, Atlanta, GA 30318",
                "lat": 33.7701,
                "lng": -84.4324,
                "location": {"type": "Point", "coordinates": [-84.4324, 33.7701]},
                "hours_notes": "Mon-Fri 8am-4pm",
                "eligibility_rules": ["No ID Required", "Atlanta Residents"],
                "inventory_status": "High",
                "status": "OPEN",
                "hours_today": "8am-4pm",
                "is_id_required": False,
                "residency_req": "Atlanta residents",
                "special_notes": None,
                "confidence": 8,
                "source_url": "https://acfb.org",
                "last_updated": "2024-01-15T10:30:00Z"
            }
        }
    }


class PantryCreate(BaseModel):
    """Schema for creating a new pantry (without id field)"""
    name: str
    address: str
    lat: float
    lng: float
    location: Optional[GeoJSONPoint] = None
    hours_notes: str
    eligibility_rules: List[str] = Field(default_factory=list)
    inventory_status: InventoryStatus = Field(default=InventoryStatus.MEDIUM)
    status: PantryStatus = Field(default=PantryStatus.UNKNOWN)
    hours_today: Optional[str] = None
    is_id_required: Optional[bool] = None
    residency_req: Optional[str] = None
    special_notes: Optional[str] = None
    confidence: Optional[int] = None
    source_url: Optional[str] = None
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PantryUpdate(BaseModel):
    """
    Schema for structured data extracted from scraped pantry content
    via Azure OpenAI Structured Outputs.
    """
    status: PantryStatus = Field(
        description="Current operational status: OPEN if the pantry is actively serving, CLOSED if temporarily/permanently closed, WAITLIST if they mention limited capacity or waiting lists, UNKNOWN only if the page has no relevant info at all"
    )
    hours_notes: str = Field(
        description="Full weekly operating schedule extracted from the page, e.g. 'Mon-Fri 9am-5pm, Sat 10am-2pm'. Include all days and times mentioned. If not found, return 'Not listed on website'"
    )
    hours_today: str = Field(
        description="Today's specific hours based on the schedule, e.g. '9am-5pm'. If the schedule is listed but today is not included, return 'Closed today'. If no schedule found, return 'Not listed'"
    )
    eligibility_rules: List[str] = Field(
        description="List of ALL eligibility requirements, restrictions, or conditions mentioned. Examples: 'Must live in Fulton County', 'Photo ID required', 'One visit per month', 'Seniors 65+ priority', 'Open to all'. Extract every specific rule. If none mentioned, return ['Open to all']"
    )
    is_id_required: bool = Field(
        description="True if the text mentions needing ID, photo identification, driver's license, proof of address, or any documentation to receive food. False if it explicitly says 'No ID required' or mentions no documentation requirements"
    )
    residency_req: Optional[str] = Field(
        default=None,
        description="Specific geographic requirement like 'Fulton County residents', 'Atlanta zip codes 30308-30312', 'Midtown area'. None if open to everyone"
    )
    special_notes: Optional[str] = Field(
        default=None,
        description="Important alerts: temporary closures, holiday schedules, 'arrive early', capacity limits, special distributions. None if nothing noteworthy"
    )
    confidence: int = Field(
        description="1-10: How much food-pantry-specific information was on this page. 1=generic church site with no pantry details. 5=some mentions of food programs. 9-10=dedicated food pantry page with hours, rules, etc."
    )
