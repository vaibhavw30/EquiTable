"""
Tests for DiscoveryService — live pantry discovery orchestration.

All tests use mocked PlacesClient and IngestionPipeline. DB tests use
the test_db fixture from conftest.py (real MongoDB Atlas test database).
"""

import asyncio
from datetime import datetime, timezone, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from models.discovery import PlaceResult, DiscoveryStatus
from models.pantry import PantryUpdate, PantryStatus, make_geojson_point
from services.discovery_service import (
    DiscoveryService,
    clear_job_state,
    FRESHNESS_HOURS,
    _parse_city_state,
)
from services.ingestion_pipeline import IngestionPipeline, IngestionError
from services.places_client import PlacesClient, PlacesAPIError


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_place(
    name="Test Food Bank",
    address="123 Main St, Denver, CO 80202, USA",
    lat=39.7392,
    lng=-104.9903,
    website_url="https://testfoodbank.org",
    place_id="place_abc",
) -> PlaceResult:
    return PlaceResult(
        name=name,
        address=address,
        lat=lat,
        lng=lng,
        website_url=website_url,
        place_id=place_id,
    )


def _make_pantry_update(**overrides) -> PantryUpdate:
    defaults = {
        "status": PantryStatus.OPEN,
        "hours_notes": "Mon-Fri 9am-5pm",
        "hours_today": "9am-5pm",
        "eligibility_rules": ["Open to all"],
        "is_id_required": False,
        "confidence": 8,
    }
    defaults.update(overrides)
    return PantryUpdate(**defaults)


def _make_service(
    places_results=None,
    pipeline_result=None,
    pipeline_error=None,
    db=None,
) -> DiscoveryService:
    """Create a DiscoveryService with mocked dependencies."""
    places = MagicMock(spec=PlacesClient)
    places.search_multi_query = AsyncMock(return_value=places_results or [])
    # Backward compat — some tests still use search_nearby
    places.search_nearby = AsyncMock(return_value=places_results or [])
    # Default: Place Details returns no website
    places.get_place_website = AsyncMock(return_value=None)

    pipeline = MagicMock(spec=IngestionPipeline)
    if pipeline_error:
        pipeline.ingest = AsyncMock(side_effect=pipeline_error)
    else:
        pipeline.ingest = AsyncMock(return_value=pipeline_result or _make_pantry_update())

    return DiscoveryService(places_client=places, pipeline=pipeline, db=db)


async def _collect_events(service, job_id, max_events=50):
    """Collect all SSE events from a job stream."""
    events = []
    async for event in service.event_stream(job_id):
        if event["event"] == "heartbeat":
            continue
        events.append(event)
        if event["event"] in ("complete", "error") or len(events) >= max_events:
            break
    return events


# ── Test: Address Parsing ────────────────────────────────────────────────────


class TestAddressParsing:
    def test_full_us_address(self):
        city, state = _parse_city_state("123 Main St, Denver, CO 80202, USA")
        assert city == "Denver"
        assert state == "CO"

    def test_short_address(self):
        city, state = _parse_city_state("Denver, CO 80202")
        assert city == "Denver"
        assert state == "CO"

    def test_empty_address(self):
        city, state = _parse_city_state("")
        assert city is None
        assert state is None

    def test_none_address(self):
        city, state = _parse_city_state(None)
        assert city is None
        assert state is None


# ── Test: PlacesClient Integration (dedup logic) ────────────────────────────


class TestDeduplication:
    """Test dedup logic against a real test DB."""

    @pytest.fixture(autouse=True)
    def _clear_jobs(self):
        clear_job_state()
        yield
        clear_job_state()

    @pytest.mark.asyncio
    async def test_new_url_is_not_skipped(self, test_db):
        """Places result with a URL not in DB should be marked for scraping."""
        service = _make_service(db=test_db)
        places = [_make_place(website_url="https://brand-new-pantry.org")]

        to_scrape, to_store_basic, skipped = await service._deduplicate(places)

        assert len(to_scrape) == 1
        assert len(to_store_basic) == 0
        assert len(skipped) == 0
        assert to_scrape[0].website_url == "https://brand-new-pantry.org"

    @pytest.mark.asyncio
    async def test_fresh_url_is_skipped(self, test_db):
        """URL already in DB with recent last_updated should be skipped."""
        await test_db["pantries"].insert_one({
            "name": "Existing Pantry",
            "address": "123 Main St",
            "lat": 39.7392,
            "lng": -104.9903,
            "location": make_geojson_point(39.7392, -104.9903).model_dump(),
            "source_url": "https://existing-pantry.org",
            "last_updated": datetime.now(timezone.utc),
            "status": "OPEN",
            "hours_notes": "Mon-Fri",
            "confidence": 8,
        })

        service = _make_service(db=test_db)
        places = [_make_place(website_url="https://existing-pantry.org")]

        to_scrape, to_store_basic, skipped = await service._deduplicate(places)

        assert len(to_scrape) == 0
        assert len(to_store_basic) == 0
        assert len(skipped) == 1

    @pytest.mark.asyncio
    async def test_stale_url_is_rescraped(self, test_db):
        """URL in DB with old last_updated should be marked for re-scraping."""
        stale_time = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_HOURS + 1)
        await test_db["pantries"].insert_one({
            "name": "Stale Pantry",
            "address": "456 Old St",
            "lat": 39.74,
            "lng": -104.99,
            "location": make_geojson_point(39.74, -104.99).model_dump(),
            "source_url": "https://stale-pantry.org",
            "last_updated": stale_time,
            "status": "UNKNOWN",
            "hours_notes": "Unknown",
            "confidence": 3,
        })

        service = _make_service(db=test_db)
        places = [_make_place(website_url="https://stale-pantry.org")]

        to_scrape, to_store_basic, skipped = await service._deduplicate(places)

        assert len(to_scrape) == 1
        assert len(skipped) == 0

    @pytest.mark.asyncio
    async def test_no_website_goes_to_store_basic(self, test_db):
        """Place without a website URL (and no Place Details result) goes to to_store_basic."""
        service = _make_service(db=test_db)
        # get_place_website returns None (no website found)
        service._places.get_place_website = AsyncMock(return_value=None)
        places = [_make_place(website_url=None)]

        to_scrape, to_store_basic, skipped = await service._deduplicate(places)

        assert len(to_scrape) == 0
        assert len(to_store_basic) == 1
        assert len(skipped) == 0

    @pytest.mark.asyncio
    async def test_no_website_with_place_details_fallback(self, test_db):
        """Place without website but Place Details returns one → goes to to_scrape."""
        service = _make_service(db=test_db)
        service._places.get_place_website = AsyncMock(return_value="https://found-via-details.org")
        places = [_make_place(website_url=None, place_id="detail_test")]

        to_scrape, to_store_basic, skipped = await service._deduplicate(places)

        assert len(to_scrape) == 1
        assert len(to_store_basic) == 0
        assert to_scrape[0].website_url == "https://found-via-details.org"

    @pytest.mark.asyncio
    async def test_mixed_fresh_and_new(self, test_db):
        """Mix of fresh, stale, and new URLs correctly sorted."""
        await test_db["pantries"].insert_one({
            "name": "Fresh",
            "address": "1 St",
            "lat": 39.7,
            "lng": -104.9,
            "location": make_geojson_point(39.7, -104.9).model_dump(),
            "source_url": "https://fresh.org",
            "last_updated": datetime.now(timezone.utc),
            "status": "OPEN",
            "hours_notes": "Daily",
            "confidence": 9,
        })

        service = _make_service(db=test_db)
        places = [
            _make_place(name="Fresh", website_url="https://fresh.org"),
            _make_place(name="Brand New", website_url="https://new.org"),
        ]

        to_scrape, to_store_basic, skipped = await service._deduplicate(places)

        assert len(to_scrape) == 1
        assert to_scrape[0].website_url == "https://new.org"
        assert len(skipped) == 1
        assert skipped[0].website_url == "https://fresh.org"


# ── Test: Discovery Flow ────────────────────────────────────────────────────


class TestDiscoveryFlow:
    """Test end-to-end discovery flow with mocked dependencies."""

    @pytest.fixture(autouse=True)
    def _clear_jobs(self):
        clear_job_state()
        yield
        clear_job_state()

    @pytest.mark.asyncio
    async def test_discovery_with_zero_results(self, test_db):
        """Discovery with no Places results completes with found=0."""
        service = _make_service(places_results=[], db=test_db)

        status = await service.start_job("Empty Town", 0, 0)
        assert status.status == DiscoveryStatus.RUNNING

        events = await _collect_events(service, status.job_id)

        event_types = [e["event"] for e in events]
        assert "job_started" in event_types
        assert "complete" in event_types

        complete = next(e for e in events if e["event"] == "complete")
        assert complete["data"]["found"] == 0

    @pytest.mark.asyncio
    async def test_discovery_happy_path(self, test_db):
        """Full discovery: 2 places found, both scraped successfully."""
        places = [
            _make_place(name="Pantry A", website_url="https://pantry-a.org", place_id="a"),
            _make_place(name="Pantry B", website_url="https://pantry-b.org", place_id="b"),
        ]

        service = _make_service(
            places_results=places,
            pipeline_result=_make_pantry_update(confidence=8),
            db=test_db,
        )

        status = await service.start_job("Denver, CO", 39.7392, -104.9903)
        events = await _collect_events(service, status.job_id)

        discovered = [e for e in events if e["event"] == "pantry_discovered"]
        assert len(discovered) == 2

        complete = next(e for e in events if e["event"] == "complete")
        assert complete["data"]["found"] == 2
        assert complete["data"]["failed"] == 0

        count = await test_db["pantries"].count_documents({})
        assert count == 2

    @pytest.mark.asyncio
    async def test_discovery_with_scrape_failure(self, test_db):
        """One URL fails scraping — still processes the other."""
        places = [
            _make_place(name="Good Pantry", website_url="https://good.org", place_id="g"),
            _make_place(name="Bad Pantry", website_url="https://bad.org", place_id="b"),
        ]

        async def mock_ingest(url):
            if "bad.org" in url:
                raise IngestionError("scrape", "Timeout", url)
            return _make_pantry_update()

        pipeline = MagicMock(spec=IngestionPipeline)
        pipeline.ingest = AsyncMock(side_effect=mock_ingest)

        places_mock = MagicMock(spec=PlacesClient)
        places_mock.search_multi_query = AsyncMock(return_value=places)
        places_mock.get_place_website = AsyncMock(return_value=None)

        service = DiscoveryService(
            places_client=places_mock,
            pipeline=pipeline,
            db=test_db,
        )

        status = await service.start_job("Denver", 39.7, -104.9)
        events = await _collect_events(service, status.job_id)

        discovered = [e for e in events if e["event"] == "pantry_discovered"]
        failed = [e for e in events if e["event"] == "pantry_failed"]
        assert len(discovered) == 1
        assert len(failed) == 1
        assert failed[0]["data"]["stage"] == "scrape"

    @pytest.mark.asyncio
    async def test_discovery_all_fail(self, test_db):
        """All URLs fail — job completes with found=0, failed=N."""
        places = [
            _make_place(name="Fail 1", website_url="https://fail1.org"),
            _make_place(name="Fail 2", website_url="https://fail2.org"),
        ]

        service = _make_service(
            places_results=places,
            pipeline_error=IngestionError("scrape", "Timeout", "url"),
            db=test_db,
        )

        status = await service.start_job("Denver", 39.7, -104.9)
        events = await _collect_events(service, status.job_id)

        complete = next(e for e in events if e["event"] == "complete")
        assert complete["data"]["found"] == 0
        assert complete["data"]["failed"] == 2

    @pytest.mark.asyncio
    async def test_discovery_skips_fresh_pantries(self, test_db):
        """Fresh pantries in DB are skipped, not re-scraped."""
        await test_db["pantries"].insert_one({
            "name": "Already Fresh",
            "address": "123 St, Denver, CO 80202, USA",
            "lat": 39.7392,
            "lng": -104.9903,
            "location": make_geojson_point(39.7392, -104.9903).model_dump(),
            "source_url": "https://already-fresh.org",
            "last_updated": datetime.now(timezone.utc),
            "status": "OPEN",
            "hours_notes": "Daily",
            "confidence": 9,
        })

        places = [
            _make_place(name="Already Fresh", website_url="https://already-fresh.org"),
            _make_place(name="Brand New", website_url="https://brand-new.org"),
        ]

        service = _make_service(
            places_results=places,
            pipeline_result=_make_pantry_update(),
            db=test_db,
        )

        status = await service.start_job("Denver", 39.7, -104.9)
        events = await _collect_events(service, status.job_id)

        skipped = [e for e in events if e["event"] == "pantry_skipped"]
        discovered = [e for e in events if e["event"] == "pantry_discovered"]

        assert len(skipped) == 1
        assert skipped[0]["data"]["reason"] == "already_fresh"
        assert len(discovered) == 1

    @pytest.mark.asyncio
    async def test_discovery_stores_pantry_in_db(self, test_db):
        """Discovered pantry is upserted with correct fields."""
        places = [
            _make_place(
                name="Denver Rescue Mission",
                address="1130 Park Ave W, Denver, CO 80205, USA",
                lat=39.7434,
                lng=-105.0003,
                website_url="https://denverrescue.org",
            ),
        ]

        service = _make_service(
            places_results=places,
            pipeline_result=_make_pantry_update(
                status=PantryStatus.OPEN,
                confidence=8,
                hours_notes="Mon-Fri 9am-5pm",
            ),
            db=test_db,
        )

        status = await service.start_job("Denver", 39.7, -104.9)
        await _collect_events(service, status.job_id)

        doc = await test_db["pantries"].find_one({"source_url": "https://denverrescue.org"})
        assert doc is not None
        assert doc["name"] == "Denver Rescue Mission"
        assert doc["city"] == "Denver"
        assert doc["state"] == "CO"
        assert doc["confidence"] == 8
        assert doc["status"] == "OPEN"
        assert doc["discovered_via"] == "discovery"

    @pytest.mark.asyncio
    async def test_places_api_failure_emits_error(self, test_db):
        """Places API failure results in error event and failed status."""
        service = _make_service(db=test_db)
        service._places.search_multi_query = AsyncMock(
            side_effect=PlacesAPIError(500, "Internal server error")
        )

        status = await service.start_job("Denver", 39.7, -104.9)
        events = await _collect_events(service, status.job_id)

        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) == 1
        assert "search this area" in error_events[0]["data"]["message"].lower()

        final_status = await service.get_status(status.job_id)
        assert final_status.status == DiscoveryStatus.FAILED

    @pytest.mark.asyncio
    async def test_no_website_places_stored_with_google_places_only(self, test_db):
        """Places without websites are stored with confidence=3 and google_places_only=True."""
        places = [
            _make_place(
                name="Church Pantry",
                address="456 Church St, Denver, CO 80202, USA",
                website_url=None,
                place_id="church_1",
            ),
            _make_place(
                name="Good Pantry",
                website_url="https://good.org",
                place_id="good_1",
            ),
        ]

        places_mock = MagicMock(spec=PlacesClient)
        places_mock.search_multi_query = AsyncMock(return_value=places)
        places_mock.get_place_website = AsyncMock(return_value=None)

        pipeline = MagicMock(spec=IngestionPipeline)
        pipeline.ingest = AsyncMock(return_value=_make_pantry_update(confidence=8))

        service = DiscoveryService(
            places_client=places_mock,
            pipeline=pipeline,
            db=test_db,
        )

        status = await service.start_job("Denver", 39.7, -104.9)
        events = await _collect_events(service, status.job_id)

        discovered = [e for e in events if e["event"] == "pantry_discovered"]
        # 1 scraped + 1 google_places_only
        assert len(discovered) == 2

        # Check the google_places_only event
        gpo_events = [e for e in discovered if e["data"].get("google_places_only")]
        assert len(gpo_events) == 1
        assert gpo_events[0]["data"]["confidence"] == 3

        # Check DB document
        docs = await test_db["pantries"].find({}).to_list(length=10)
        gpo_doc = next((d for d in docs if d.get("google_places_only")), None)
        assert gpo_doc is not None
        assert gpo_doc["name"] == "Church Pantry"
        assert gpo_doc["confidence"] == 3
        assert gpo_doc["google_places_only"] is True


class TestJobStatus:
    """Test job status retrieval."""

    @pytest.fixture(autouse=True)
    def _clear_jobs(self):
        clear_job_state()
        yield
        clear_job_state()

    @pytest.mark.asyncio
    async def test_get_status_returns_none_for_unknown(self):
        service = _make_service()
        status = await service.get_status("nonexistent-job-id")
        assert status is None

    @pytest.mark.asyncio
    async def test_get_status_after_start(self, test_db):
        service = _make_service(places_results=[], db=test_db)
        status = await service.start_job("Denver", 39.7, -104.9)
        retrieved = await service.get_status(status.job_id)
        assert retrieved is not None
        assert retrieved.query == "Denver"

    @pytest.mark.asyncio
    async def test_completed_stream_returns_summary(self, test_db):
        """Connecting to a completed job's stream returns the complete event."""
        service = _make_service(places_results=[], db=test_db)
        status = await service.start_job("Denver", 39.7, -104.9)

        await _collect_events(service, status.job_id)

        events = await _collect_events(service, status.job_id)
        assert any(e["event"] == "complete" for e in events)


class TestBasicPlaceStorage:
    """Test fallback storage when scraping fails."""

    @pytest.fixture(autouse=True)
    def _clear_jobs(self):
        clear_job_state()
        yield
        clear_job_state()

    @pytest.mark.asyncio
    async def test_failed_scrape_stores_basic_data(self, test_db):
        """When scraping fails, basic Places API data is stored with confidence=3."""
        places = [
            _make_place(
                name="Failing Pantry",
                address="789 Fail St, Denver, CO 80202, USA",
                website_url="https://failing.org",
            ),
        ]

        service = _make_service(
            places_results=places,
            pipeline_error=IngestionError("scrape", "Timeout", "https://failing.org"),
            db=test_db,
        )

        status = await service.start_job("Denver", 39.7, -104.9)
        await _collect_events(service, status.job_id)

        doc = await test_db["pantries"].find_one({"source_url": "https://failing.org"})
        assert doc is not None
        assert doc["name"] == "Failing Pantry"
        assert doc["confidence"] == 3
        assert doc["status"] == "UNKNOWN"
        assert doc["discovered_via"] == "discovery"
