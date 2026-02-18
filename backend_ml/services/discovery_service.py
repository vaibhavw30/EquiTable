"""
Discovery Service - Orchestrates live pantry discovery for a location.

Takes a location, finds food pantry URLs via Google Places API,
deduplicates against existing DB entries, then runs the existing
IngestionPipeline (scrape → extract → validate) for each new URL.

Results are emitted as events (dicts) via an async generator so the
route layer can stream them as SSE. This service does NOT define
routes — that's the backend agent's domain.

See docs/specs/live-discovery.md for the full spec.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator, Optional

from models.discovery import (
    DiscoveryJobStatus,
    DiscoveryStatus,
    PlaceResult,
)
from models.pantry import Pantry, PantryStatus, make_geojson_point
from services.ingestion_pipeline import IngestionPipeline, IngestionError
from services.places_client import PlacesClient, PlacesAPIError

logger = logging.getLogger("equitable")

# ── Constants ────────────────────────────────────────────────────────────────

MAX_CONCURRENT_SCRAPES = 3
MAX_URLS_PER_JOB = 10
FRESHNESS_HOURS = 24
JOB_TIMEOUT_SECONDS = 120


# ── In-memory job state (keyed by job_id) ────────────────────────────────────
# Each running job gets an asyncio.Queue for SSE events plus a status dict.

_job_queues: dict[str, asyncio.Queue] = {}
_job_statuses: dict[str, DiscoveryJobStatus] = {}


def _parse_city_state(address: str) -> tuple[Optional[str], Optional[str]]:
    """
    Best-effort extraction of city and state from a formatted address.
    Google Places returns addresses like "123 Main St, Denver, CO 80202, USA".
    Also handles shorter forms like "Denver, CO 80202".
    """
    if not address:
        return None, None

    parts = [p.strip() for p in address.split(",")]

    if len(parts) >= 3:
        # Typically: [street, city, "STATE ZIP", country]
        # or: [street, city, "STATE ZIP"]
        city = parts[-3] if len(parts) >= 4 else parts[-2]
        state_zip = parts[-2] if len(parts) >= 4 else parts[-1]
        state = state_zip.split()[0] if state_zip else None
        # Validate state is 2-letter abbreviation
        if state and len(state) == 2 and state.isalpha():
            return city, state.upper()
        return city, None

    if len(parts) == 2:
        # "Denver, CO 80202" or "Denver, CO"
        city = parts[0]
        state_zip = parts[1].strip()
        state = state_zip.split()[0] if state_zip else None
        if state and len(state) == 2 and state.isalpha():
            return city, state.upper()
        return city, None

    return None, None


class DiscoveryService:
    """
    Coordinates live pantry discovery for a geographic area.

    Flow:
    1. Search Google Places for food pantries near the target location
    2. Deduplicate against existing DB entries (by source_url or name+proximity)
    3. Run IngestionPipeline for each new URL (scrape → extract → validate)
    4. Yield SSE events as each pantry completes or fails
    """

    def __init__(
        self,
        places_client: PlacesClient,
        pipeline: IngestionPipeline,
        db=None,
    ):
        self._places = places_client
        self._pipeline = pipeline
        self._db = db  # MongoDB database instance (injected for testability)

    def _get_pantries_collection(self):
        """Get pantries collection, using injected db or falling back to global."""
        if self._db is not None:
            return self._db["pantries"]
        from database import get_collection
        return get_collection("pantries")

    def _get_jobs_collection(self):
        """Get discovery_jobs collection."""
        if self._db is not None:
            return self._db["discovery_jobs"]
        from database import get_collection
        return get_collection("discovery_jobs")

    # ── Public API ──────────────────────────────────────────────────────────

    async def start_job(
        self,
        query: str,
        lat: float,
        lng: float,
        radius_meters: int = 8000,
        client_ip: str = "unknown",
    ) -> DiscoveryJobStatus:
        """
        Start a new discovery job. Returns the job status immediately.
        The actual discovery runs as a background task.

        Raises:
            PlacesAPIError: If the Places API call fails.
        """
        job_id = str(uuid.uuid4())

        status = DiscoveryJobStatus(
            job_id=job_id,
            status=DiscoveryStatus.RUNNING,
            query=query,
        )

        _job_statuses[job_id] = status
        _job_queues[job_id] = asyncio.Queue()

        logger.info(
            "Discovery job started",
            extra={
                "event": "discovery_start",
                "job_id": job_id,
                "query": query,
                "lat": lat,
                "lng": lng,
                "radius_meters": radius_meters,
            },
        )

        # Launch the actual discovery in the background
        asyncio.create_task(
            self._run_discovery(job_id, query, lat, lng, radius_meters)
        )

        return status

    async def get_status(self, job_id: str) -> Optional[DiscoveryJobStatus]:
        """Get the current status of a discovery job."""
        return _job_statuses.get(job_id)

    async def event_stream(self, job_id: str) -> AsyncGenerator[dict, None]:
        """
        Async generator that yields SSE events for a discovery job.
        Yields dicts with 'event' and 'data' keys.

        If the job is already completed, yields a single 'complete' event.
        """
        status = _job_statuses.get(job_id)
        if status is None:
            yield {"event": "error", "data": {"message": "Job not found"}}
            return

        # If job already finished, return summary
        if status.status != DiscoveryStatus.RUNNING:
            yield self._make_complete_event(status)
            return

        queue = _job_queues.get(job_id)
        if queue is None:
            yield {"event": "error", "data": {"message": "Job queue not found"}}
            return

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
                if event is None:
                    # Sentinel: stream is done
                    break
                yield event
            except asyncio.TimeoutError:
                # Heartbeat to keep connection alive
                yield {"event": "heartbeat", "data": {}}

    async def count_fresh_pantries(
        self, lat: float, lng: float, radius_meters: int
    ) -> int:
        """Count pantries near a location that were updated within FRESHNESS_HOURS."""
        collection = self._get_pantries_collection()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_HOURS)

        count = await collection.count_documents({
            "location": {
                "$near": {
                    "$geometry": {
                        "type": "Point",
                        "coordinates": [lng, lat],
                    },
                    "$maxDistance": radius_meters,
                }
            },
            "last_updated": {"$gte": cutoff},
        })
        return count

    # ── Internal discovery logic ────────────────────────────────────────────

    async def _run_discovery(
        self,
        job_id: str,
        query: str,
        lat: float,
        lng: float,
        radius_meters: int,
    ):
        """
        The main discovery coroutine. Runs as a background task.

        1. Call Places API to find URLs
        2. Deduplicate against DB
        3. Scrape each new URL via IngestionPipeline
        4. Push events to the job's queue
        """
        status = _job_statuses[job_id]
        queue = _job_queues[job_id]
        start = time.time()

        try:
            # Phase 1: Find URLs via Places API
            places = await self._find_urls(query, lat, lng, radius_meters)
            status.urls_found = len(places)

            await queue.put({
                "event": "job_started",
                "data": {
                    "job_id": job_id,
                    "query": query,
                    "urls_found": len(places),
                },
            })

            if not places:
                status.status = DiscoveryStatus.COMPLETED
                status.completed_at = datetime.now(timezone.utc)
                status.duration_ms = round((time.time() - start) * 1000)
                await queue.put(self._make_complete_event(status))
                await queue.put(None)
                return

            # Phase 2: Deduplicate — figure out which URLs need scraping
            to_scrape, to_store_basic, skipped = await self._deduplicate(places)
            status.urls_skipped = len(skipped)

            for place in skipped:
                await queue.put({
                    "event": "pantry_skipped",
                    "data": {
                        "source_url": place.website_url or "",
                        "name": place.name,
                        "reason": "already_fresh",
                    },
                })

            # Phase 2b: Store places without websites (Google Places data only)
            for place in to_store_basic:
                pantry_data = await self._store_basic_place(place)
                if pantry_data:
                    status.urls_processed += 1
                    status.urls_succeeded += 1
                    await queue.put({
                        "event": "pantry_discovered",
                        "data": {
                            "pantry_id": pantry_data.get("_id", ""),
                            "name": place.name,
                            "address": place.address,
                            "lat": place.lat,
                            "lng": place.lng,
                            "status": "UNKNOWN",
                            "confidence": 3,
                            "source_url": None,
                            "google_places_only": True,
                        },
                    })
                    await queue.put({
                        "event": "progress",
                        "data": {
                            "processed": status.urls_processed,
                            "total": len(to_scrape) + len(to_store_basic),
                            "succeeded": status.urls_succeeded,
                            "failed": status.urls_failed,
                        },
                    })

            # Phase 3: Scrape in parallel with concurrency limit
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCRAPES)

            async def process_one(place: PlaceResult):
                async with semaphore:
                    await self._process_place(
                        job_id, place, lat, lng, queue, status
                    )

            # Create tasks with a global timeout
            tasks = [asyncio.create_task(process_one(p)) for p in to_scrape]

            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=JOB_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                # Cancel remaining tasks
                for t in tasks:
                    if not t.done():
                        t.cancel()
                status.status = DiscoveryStatus.TIMED_OUT
                logger.warning(
                    "Discovery job timed out",
                    extra={"event": "discovery_timeout", "job_id": job_id},
                )

            # Phase 4: Complete
            if status.status == DiscoveryStatus.RUNNING:
                status.status = DiscoveryStatus.COMPLETED

            status.completed_at = datetime.now(timezone.utc)
            status.duration_ms = round((time.time() - start) * 1000)

            await queue.put(self._make_complete_event(status))

            logger.info(
                "Discovery job complete",
                extra={
                    "event": "discovery_complete",
                    "job_id": job_id,
                    "urls_found": status.urls_found,
                    "succeeded": status.urls_succeeded,
                    "failed": status.urls_failed,
                    "skipped": status.urls_skipped,
                    "duration_ms": status.duration_ms,
                },
            )

        except PlacesAPIError as e:
            status.status = DiscoveryStatus.FAILED
            status.error = e.message
            status.completed_at = datetime.now(timezone.utc)
            status.duration_ms = round((time.time() - start) * 1000)

            await queue.put({
                "event": "error",
                "data": {"message": f"Could not search this area: {e.message}"},
            })

            logger.error(
                "Discovery job failed",
                extra={
                    "event": "discovery_failed",
                    "job_id": job_id,
                    "error": e.message,
                },
            )

        except Exception as e:
            status.status = DiscoveryStatus.FAILED
            status.error = str(e)
            status.completed_at = datetime.now(timezone.utc)
            status.duration_ms = round((time.time() - start) * 1000)

            await queue.put({
                "event": "error",
                "data": {"message": "Discovery failed unexpectedly"},
            })

            logger.error(
                "Discovery job failed",
                extra={
                    "event": "discovery_failed",
                    "job_id": job_id,
                    "error": str(e),
                },
                exc_info=True,
            )

        finally:
            await queue.put(None)  # Sentinel to close the stream
            # Clean up queue after a delay (let clients read the complete event)
            await asyncio.sleep(60)
            _job_queues.pop(job_id, None)

    async def _find_urls(
        self,
        query: str,
        lat: float,
        lng: float,
        radius_meters: int,
    ) -> list[PlaceResult]:
        """Call Places API with multiple queries and return deduped results."""
        results = await self._places.search_multi_query(
            lat=lat,
            lng=lng,
            radius_meters=radius_meters,
            max_results=MAX_URLS_PER_JOB,
        )
        return results

    async def _deduplicate(
        self,
        places: list[PlaceResult],
    ) -> tuple[list[PlaceResult], list[PlaceResult], list[PlaceResult]]:
        """
        Split places into (to_scrape, to_store_basic, skipped) based on DB state.

        Returns 3 lists:
        - to_scrape: has website URL, not fresh in DB → full pipeline
        - to_store_basic: no website URL (even after Place Details fallback) → store with confidence=3
        - skipped: fresh in DB → already up-to-date

        For places without a website URL, tries Place Details API as fallback.
        """
        collection = self._get_pantries_collection()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_HOURS)

        to_scrape = []
        to_store_basic = []
        skipped = []

        for place in places:
            # If no website, try Place Details fallback
            if not place.website_url:
                website = await self._places.get_place_website(place.place_id)
                if website:
                    place = PlaceResult(
                        name=place.name,
                        address=place.address,
                        lat=place.lat,
                        lng=place.lng,
                        website_url=website,
                        place_id=place.place_id,
                    )
                else:
                    # Check if already in DB by name + proximity
                    name_match = await collection.find_one({
                        "name": {"$regex": f"^{_escape_regex(place.name)}$", "$options": "i"},
                        "location": {
                            "$near": {
                                "$geometry": {
                                    "type": "Point",
                                    "coordinates": [place.lng, place.lat],
                                },
                                "$maxDistance": 200,
                            }
                        },
                        "last_updated": {"$gte": cutoff},
                    })
                    if name_match:
                        skipped.append(place)
                    else:
                        to_store_basic.append(place)
                    continue

            # Check if this URL already exists and is fresh
            existing = await collection.find_one({
                "source_url": place.website_url,
            })

            if existing:
                last_updated = existing.get("last_updated")
                if isinstance(last_updated, str):
                    last_updated = datetime.fromisoformat(
                        last_updated.replace("Z", "+00:00")
                    )
                # MongoDB may store timezone-naive datetimes — normalize
                if isinstance(last_updated, datetime) and last_updated.tzinfo is None:
                    last_updated = last_updated.replace(tzinfo=timezone.utc)

                if last_updated and last_updated >= cutoff:
                    skipped.append(place)
                    continue

            # Also check by name + proximity (within ~500m)
            name_match = await collection.find_one({
                "name": {"$regex": f"^{_escape_regex(place.name)}$", "$options": "i"},
                "location": {
                    "$near": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [place.lng, place.lat],
                        },
                        "$maxDistance": 500,
                    }
                },
                "last_updated": {"$gte": cutoff},
            })

            if name_match:
                skipped.append(place)
                continue

            to_scrape.append(place)

        return to_scrape, to_store_basic, skipped

    async def _process_place(
        self,
        job_id: str,
        place: PlaceResult,
        search_lat: float,
        search_lng: float,
        queue: asyncio.Queue,
        status: DiscoveryJobStatus,
    ):
        """
        Process a single place: scrape → extract → validate → store.
        Emits SSE events for success or failure.
        """
        url = place.website_url
        if not url:
            status.urls_processed += 1
            status.urls_failed += 1
            return

        try:
            # Run existing IngestionPipeline — no modifications needed
            update = await self._pipeline.ingest(url)

            # Merge Places API metadata with extraction results
            city, state = _parse_city_state(place.address)

            doc = {
                # From Places API (authoritative for identity)
                "name": place.name,
                "address": place.address,
                "lat": place.lat,
                "lng": place.lng,
                "location": make_geojson_point(place.lat, place.lng).model_dump(),
                "city": city,
                "state": state,
                "source_url": url,
                "discovered_via": "discovery",
                "last_updated": datetime.now(timezone.utc),
                # From IngestionPipeline (extracted content)
                "status": update.status,
                "hours_notes": update.hours_notes,
                "hours_today": update.hours_today,
                "eligibility_rules": update.eligibility_rules,
                "is_id_required": update.is_id_required,
                "residency_req": update.residency_req,
                "special_notes": update.special_notes,
                "confidence": update.confidence,
            }

            # Upsert by source_url
            collection = self._get_pantries_collection()
            result = await collection.update_one(
                {"source_url": url},
                {"$set": doc, "$setOnInsert": {"inventory_status": "Medium"}},
                upsert=True,
            )

            # Get the pantry ID (either inserted or updated)
            if result.upserted_id:
                pantry_id = str(result.upserted_id)
            else:
                existing = await collection.find_one({"source_url": url})
                pantry_id = str(existing["_id"]) if existing else ""

            status.urls_processed += 1
            status.urls_succeeded += 1
            status.pantry_ids.append(pantry_id)

            await queue.put({
                "event": "pantry_discovered",
                "data": {
                    "pantry_id": pantry_id,
                    "name": place.name,
                    "address": place.address,
                    "lat": place.lat,
                    "lng": place.lng,
                    "status": update.status,
                    "confidence": update.confidence,
                    "source_url": url,
                },
            })

            await queue.put({
                "event": "progress",
                "data": {
                    "processed": status.urls_processed,
                    "total": status.urls_found - status.urls_skipped,
                    "succeeded": status.urls_succeeded,
                    "failed": status.urls_failed,
                },
            })

        except IngestionError as e:
            status.urls_processed += 1
            status.urls_failed += 1

            # Store basic Places API data even if scraping failed
            await self._store_basic_place(place)

            await queue.put({
                "event": "pantry_failed",
                "data": {
                    "source_url": url,
                    "name": place.name,
                    "stage": e.stage,
                    "reason": e.reason,
                },
            })

            await queue.put({
                "event": "progress",
                "data": {
                    "processed": status.urls_processed,
                    "total": status.urls_found - status.urls_skipped,
                    "succeeded": status.urls_succeeded,
                    "failed": status.urls_failed,
                },
            })

            logger.warning(
                "Discovery: pantry ingestion failed",
                extra={
                    "event": "discovery_pantry_failed",
                    "job_id": job_id,
                    "url": url,
                    "stage": e.stage,
                    "reason": e.reason,
                },
            )

        except Exception as e:
            status.urls_processed += 1
            status.urls_failed += 1

            await queue.put({
                "event": "pantry_failed",
                "data": {
                    "source_url": url or "",
                    "name": place.name,
                    "stage": "unknown",
                    "reason": str(e),
                },
            })

            logger.error(
                "Discovery: unexpected error processing place",
                extra={
                    "event": "discovery_pantry_error",
                    "job_id": job_id,
                    "url": url,
                    "error": str(e),
                },
            )

    async def _store_basic_place(self, place: PlaceResult) -> Optional[dict]:
        """
        Store a pantry with only Places API data (no scrape results).
        Sets confidence=3 to indicate minimal data quality.
        Sets google_places_only=True so frontend can show "Limited info" note.
        Used as fallback when scraping/extraction fails or no website exists.

        Returns the stored document dict (with _id) or None on failure.
        """
        collection = self._get_pantries_collection()
        city, state = _parse_city_state(place.address)

        doc = {
            "name": place.name,
            "address": place.address,
            "lat": place.lat,
            "lng": place.lng,
            "location": make_geojson_point(place.lat, place.lng).model_dump(),
            "city": city,
            "state": state,
            "discovered_via": "discovery",
            "google_places_only": place.website_url is None,
            "last_updated": datetime.now(timezone.utc),
            "status": PantryStatus.UNKNOWN.value,
            "hours_notes": "Not listed on website",
            "hours_today": "Not listed",
            "eligibility_rules": [],
            "is_id_required": None,
            "residency_req": None,
            "special_notes": None,
            "confidence": 3,
            "inventory_status": "Medium",
        }

        # Only include source_url if it's not None (avoids unique index
        # conflict on source_url: null when multiple no-website places exist)
        if place.website_url:
            doc["source_url"] = place.website_url

        try:
            if place.website_url:
                # Upsert by source_url — unique sparse index handles dedup
                result = await collection.update_one(
                    {"source_url": place.website_url},
                    {"$set": doc},
                    upsert=True,
                )
                if result.upserted_id:
                    doc["_id"] = str(result.upserted_id)
                else:
                    existing = await collection.find_one({"source_url": place.website_url})
                    if existing:
                        doc["_id"] = str(existing["_id"])
            else:
                # No source_url — check for existing by name + proximity,
                # then insert or update. Can't use $near in upsert filter.
                existing = await collection.find_one({
                    "name": {"$regex": f"^{_escape_regex(place.name)}$", "$options": "i"},
                    "location": {
                        "$near": {
                            "$geometry": {
                                "type": "Point",
                                "coordinates": [place.lng, place.lat],
                            },
                            "$maxDistance": 200,
                        }
                    },
                })
                if existing:
                    await collection.update_one(
                        {"_id": existing["_id"]},
                        {"$set": doc},
                    )
                    doc["_id"] = str(existing["_id"])
                else:
                    result = await collection.insert_one(doc)
                    doc["_id"] = str(result.inserted_id)

            return doc
        except Exception as e:
            logger.error(
                "Failed to store basic place data",
                extra={
                    "event": "discovery_store_basic_failed",
                    "place_name": place.name,
                    "error": str(e),
                },
            )
            return None

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_complete_event(status: DiscoveryJobStatus) -> dict:
        return {
            "event": "complete",
            "data": {
                "job_id": status.job_id,
                "found": status.urls_succeeded,
                "failed": status.urls_failed,
                "skipped": status.urls_skipped,
                "duration_ms": status.duration_ms,
                "timed_out": status.status == DiscoveryStatus.TIMED_OUT,
            },
        }


def _escape_regex(text: str) -> str:
    """Escape special regex characters in a string for MongoDB $regex."""
    import re
    return re.escape(text)


def clear_job_state():
    """Clear all in-memory job state. Used in tests."""
    _job_queues.clear()
    _job_statuses.clear()
