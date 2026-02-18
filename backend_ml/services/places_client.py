"""
Google Places API (New) client for discovering food pantry URLs.

Uses Text Search (New) with Enterprise field mask to get websiteUri,
displayName, formattedAddress, and location in a single call.

Supports multi-query search (4 queries deduped by place_id),
Place Details fallback for missing websites, and 7-day result caching.

See ADR-011 and ADR-014 in docs/decisions.md for evaluation and rationale.
"""

import logging
import math
import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from models.discovery import PlaceResult

logger = logging.getLogger("equitable")

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Enterprise field mask — includes websiteUri (bumps to Enterprise tier,
# but 1,000 free requests/month is plenty for our usage).
FIELD_MASK = ",".join([
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.websiteUri",
    "places.id",
])

DETAIL_FIELD_MASK = "websiteUri"

# Search queries for maximum coverage
DISCOVERY_QUERIES = [
    "food bank",
    "food pantry",
    "food distribution",
    "community food",
]


class PlacesAPIError(Exception):
    """Raised when the Google Places API call fails."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"Places API error ({status_code}): {message}")


class PlacesClient:
    """
    Wrapper around Google Places API (New) for food pantry discovery.

    Features:
    - Multi-query search (4 food-related queries, deduped by place_id)
    - Place Details fallback for missing website URLs
    - 7-day result caching via MongoDB discovery_cache collection
    """

    def __init__(self, api_key: str | None = None, db=None):
        if api_key:
            self._api_key = api_key
        else:
            import os
            self._api_key = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self._db = db

    def _get_cache_collection(self):
        """Get discovery_cache collection for caching Places API results."""
        if self._db is not None:
            return self._db["discovery_cache"]
        from database import get_collection
        return get_collection("discovery_cache")

    # ── Multi-Query Search ────────────────────────────────────────────────

    async def search_multi_query(
        self,
        lat: float,
        lng: float,
        radius_meters: int = 16000,
        max_results: int = 10,
    ) -> List[PlaceResult]:
        """
        Search for food organizations using multiple queries, deduped by place_id.

        Runs 4 queries ("food bank", "food pantry", "food distribution",
        "community food") and merges results. Checks cache first.

        Args:
            lat: Center latitude.
            lng: Center longitude.
            radius_meters: Search radius in meters.
            max_results: Maximum total results to return.

        Returns:
            List of PlaceResult deduped by place_id.

        Raises:
            PlacesAPIError: On HTTP or API errors.
        """
        start = time.time()

        logger.info(
            "Multi-query places search starting",
            extra={
                "event": "places_search_started",
                "lat": lat,
                "lng": lng,
                "radius_meters": radius_meters,
                "queries": DISCOVERY_QUERIES,
            },
        )

        # Check cache first
        cached = await self._check_cache(lat, lng, radius_meters)
        if cached is not None:
            duration_ms = round((time.time() - start) * 1000, 2)
            logger.info(
                "Places search cache hit",
                extra={
                    "event": "places_search_cache_hit",
                    "lat": lat,
                    "lng": lng,
                    "results_count": len(cached),
                    "duration_ms": duration_ms,
                },
            )
            return cached[:max_results]

        # Run all queries and deduplicate by place_id
        seen_ids = set()
        all_results = []

        for query in DISCOVERY_QUERIES:
            try:
                results = await self._text_search(
                    query=query,
                    lat=lat,
                    lng=lng,
                    radius_meters=radius_meters,
                    max_results=10,
                )
                for r in results:
                    if r.place_id and r.place_id not in seen_ids:
                        seen_ids.add(r.place_id)
                        all_results.append(r)
            except PlacesAPIError:
                # Log already handled in _text_search; continue with other queries
                continue

        duration_ms = round((time.time() - start) * 1000, 2)

        with_website = sum(1 for r in all_results if r.website_url)
        without_website = len(all_results) - with_website

        logger.info(
            "Multi-query places search complete",
            extra={
                "event": "places_search_complete",
                "lat": lat,
                "lng": lng,
                "total_results": len(all_results),
                "with_website": with_website,
                "without_website": without_website,
                "duration_ms": duration_ms,
            },
        )

        # Cache results
        await self._store_cache(lat, lng, radius_meters, all_results)

        return all_results[:max_results]

    # ── Single Query (internal) ───────────────────────────────────────────

    async def _text_search(
        self,
        query: str,
        lat: float,
        lng: float,
        radius_meters: int = 8000,
        max_results: int = 10,
    ) -> List[PlaceResult]:
        """Run a single Text Search query against Google Places API."""
        max_results = min(max_results, 10)

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        }

        body = {
            "textQuery": query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": float(radius_meters),
                }
            },
            "maxResultCount": max_results,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    TEXT_SEARCH_URL,
                    json=body,
                    headers=headers,
                    timeout=15,
                )

            if resp.status_code != 200:
                logger.error(
                    "Places text search failed",
                    extra={
                        "event": "places_search_failed",
                        "query": query,
                        "status_code": resp.status_code,
                        "error": resp.text[:500],
                    },
                )
                raise PlacesAPIError(resp.status_code, resp.text[:500])

            data = resp.json()
            results = []

            for place in data.get("places", []):
                loc = place.get("location", {})
                display_name = place.get("displayName", {})

                results.append(PlaceResult(
                    name=display_name.get("text", "Unknown"),
                    address=place.get("formattedAddress", ""),
                    lat=loc.get("latitude", 0.0),
                    lng=loc.get("longitude", 0.0),
                    website_url=place.get("websiteUri"),
                    place_id=place.get("id", ""),
                ))

            return results[:max_results]

        except httpx.HTTPError as e:
            logger.error(
                "Places text search failed",
                extra={
                    "event": "places_search_failed",
                    "query": query,
                    "error": str(e),
                },
            )
            raise PlacesAPIError(0, str(e))

    # ── Backward-compatible single search ─────────────────────────────────

    async def search_nearby(
        self,
        query: str,
        lat: float,
        lng: float,
        radius_meters: int = 8000,
        max_results: int = 10,
    ) -> List[PlaceResult]:
        """
        Search for food pantries/banks near a location (single query).
        Kept for backward compatibility with existing tests.
        """
        start = time.time()

        logger.info(
            "Places search starting",
            extra={
                "event": "places_search_start",
                "query": query,
                "lat": lat,
                "lng": lng,
                "radius_meters": radius_meters,
            },
        )

        try:
            results = await self._text_search(
                query=f"food pantry OR food bank near {query}",
                lat=lat,
                lng=lng,
                radius_meters=radius_meters,
                max_results=max_results,
            )

            duration_ms = round((time.time() - start) * 1000, 2)

            logger.info(
                "Places search complete",
                extra={
                    "event": "places_search_complete",
                    "query": query,
                    "results_count": len(results),
                    "with_website": sum(1 for r in results if r.website_url),
                    "duration_ms": duration_ms,
                },
            )

            return results

        except PlacesAPIError:
            raise
        except httpx.HTTPError as e:
            raise PlacesAPIError(0, str(e))

    # ── Place Details (website fallback) ──────────────────────────────────

    async def get_place_website(self, place_id: str) -> Optional[str]:
        """
        Fetch website URL for a place via Place Details API.

        Used as fallback when Text Search doesn't return a websiteUri.

        Args:
            place_id: Google Place ID.

        Returns:
            Website URL string or None.
        """
        url = f"https://places.googleapis.com/v1/places/{place_id}"
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": DETAIL_FIELD_MASK,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, timeout=10)

            if resp.status_code != 200:
                logger.warning(
                    "Place Details lookup failed",
                    extra={
                        "event": "place_details_failed",
                        "place_id": place_id,
                        "status_code": resp.status_code,
                    },
                )
                return None

            data = resp.json()
            return data.get("websiteUri")

        except httpx.HTTPError as e:
            logger.warning(
                "Place Details lookup failed",
                extra={
                    "event": "place_details_failed",
                    "place_id": place_id,
                    "error": str(e),
                },
            )
            return None

    # ── Cache ─────────────────────────────────────────────────────────────

    async def _check_cache(
        self, lat: float, lng: float, radius_meters: int
    ) -> Optional[List[PlaceResult]]:
        """Check discovery_cache for a recent result matching this location."""
        try:
            collection = self._get_cache_collection()
            cache_key = _make_cache_key(lat, lng, radius_meters)

            doc = await collection.find_one({"cache_key": cache_key})
            if doc is None:
                return None

            return [PlaceResult(**r) for r in doc["results"]]
        except Exception:
            # Cache failures are non-fatal
            return None

    async def _store_cache(
        self, lat: float, lng: float, radius_meters: int, results: List[PlaceResult]
    ):
        """Store Places API results in cache."""
        try:
            collection = self._get_cache_collection()
            cache_key = _make_cache_key(lat, lng, radius_meters)

            await collection.update_one(
                {"cache_key": cache_key},
                {
                    "$set": {
                        "cache_key": cache_key,
                        "lat": lat,
                        "lng": lng,
                        "radius_meters": radius_meters,
                        "results": [r.model_dump() for r in results],
                        "created_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning(
                "Failed to cache Places results",
                extra={"event": "places_cache_store_failed", "error": str(e)},
            )


def _make_cache_key(lat: float, lng: float, radius_meters: int) -> str:
    """Create a cache key from rounded coordinates + radius."""
    # Round to 2 decimal places (~1.1km precision)
    rlat = round(lat, 2)
    rlng = round(lng, 2)
    rrad = int(math.ceil(radius_meters / 1000)) * 1000  # Round radius to nearest km
    return f"{rlat},{rlng},{rrad}"
