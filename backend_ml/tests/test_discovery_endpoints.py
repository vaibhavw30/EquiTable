"""
Tests for discovery API endpoints.

Tests the route layer: POST /pantries/discover, GET .../status/{job_id},
and SSE stream. Uses mocked DiscoveryService and PlacesClient — no live
external API calls.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from models.discovery import DiscoveryJobStatus, DiscoveryStatus, PlaceResult
from models.pantry import PantryUpdate, PantryStatus, make_geojson_point
from services.discovery_service import clear_job_state


# ── Helpers ──────────────────────────────────────────────────────────────────


def _discovery_request(
    query="Denver, CO",
    lat=39.7392,
    lng=-104.9903,
    radius_meters=8000,
):
    return {
        "query": query,
        "lat": lat,
        "lng": lng,
        "radius_meters": radius_meters,
    }


def _make_place(name="Test Food Bank", website_url="https://test.org"):
    return PlaceResult(
        name=name,
        address="123 Main St, Denver, CO 80202, USA",
        lat=39.7392,
        lng=-104.9903,
        website_url=website_url,
        place_id="place_abc",
    )


# ── Test: POST /pantries/discover ────────────────────────────────────────────


class TestPostDiscover:
    @pytest.fixture(autouse=True)
    def _clear(self):
        clear_job_state()
        # Reset rate limiter between tests
        import main
        main._discovery_rate.clear()
        yield
        clear_job_state()

    @pytest.mark.asyncio
    async def test_returns_201_with_job_id(self, client, test_db):
        """Happy path: POST /pantries/discover returns 201 + job_id."""
        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.count_fresh_pantries = AsyncMock(return_value=0)
            svc.start_job = AsyncMock(return_value=DiscoveryJobStatus(
                job_id="test-job-123",
                status=DiscoveryStatus.RUNNING,
                query="Denver, CO",
            ))
            mock_svc.return_value = svc

            resp = await client.post(
                "/pantries/discover",
                json=_discovery_request(),
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["job_id"] == "test-job-123"
        assert data["status"] == "running"
        assert "stream" in data["stream_url"]

    @pytest.mark.asyncio
    async def test_invalid_lat_returns_422(self, client, test_db):
        """Invalid latitude is rejected by Pydantic validation."""
        resp = await client.post(
            "/pantries/discover",
            json=_discovery_request(lat=999),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_lng_returns_422(self, client, test_db):
        """Invalid longitude is rejected."""
        resp = await client.post(
            "/pantries/discover",
            json=_discovery_request(lng=999),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_radius_too_large_returns_422(self, client, test_db):
        """Radius > 50km is rejected by Pydantic validation."""
        resp = await client.post(
            "/pantries/discover",
            json=_discovery_request(radius_meters=100000),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_radius_too_small_returns_422(self, client, test_db):
        """Radius < 500m is rejected."""
        resp = await client.post(
            "/pantries/discover",
            json=_discovery_request(radius_meters=100),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_excess(self, client, test_db):
        """11th request within window returns 429."""
        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.count_fresh_pantries = AsyncMock(return_value=0)
            svc.start_job = AsyncMock(return_value=DiscoveryJobStatus(
                job_id="job",
                status=DiscoveryStatus.RUNNING,
                query="test",
            ))
            mock_svc.return_value = svc

            # First 10 should succeed
            for i in range(10):
                resp = await client.post(
                    "/pantries/discover",
                    json=_discovery_request(query=f"City {i}"),
                )
                assert resp.status_code == 201, f"Request {i+1} should succeed"

            # 11th should be rate limited
            resp = await client.post(
                "/pantries/discover",
                json=_discovery_request(query="City 11"),
            )
            assert resp.status_code == 429
            assert "rate limit" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_returns_existing_pantries_count(self, client, test_db):
        """Response includes count of already-fresh pantries."""
        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.count_fresh_pantries = AsyncMock(return_value=5)
            svc.start_job = AsyncMock(return_value=DiscoveryJobStatus(
                job_id="job-with-existing",
                status=DiscoveryStatus.RUNNING,
                query="Atlanta",
            ))
            mock_svc.return_value = svc

            resp = await client.post(
                "/pantries/discover",
                json=_discovery_request(query="Atlanta"),
            )

        assert resp.status_code == 201
        assert resp.json()["existing_pantries"] == 5

    @pytest.mark.asyncio
    async def test_places_api_error_returns_502(self, client, test_db):
        """Places API failure returns 502."""
        from services.places_client import PlacesAPIError

        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.count_fresh_pantries = AsyncMock(return_value=0)
            svc.start_job = AsyncMock(
                side_effect=PlacesAPIError(500, "API down")
            )
            mock_svc.return_value = svc

            resp = await client.post(
                "/pantries/discover",
                json=_discovery_request(),
            )

        assert resp.status_code == 502
        assert "search" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_missing_query_returns_422(self, client, test_db):
        """Missing required field 'query' returns 422."""
        resp = await client.post(
            "/pantries/discover",
            json={"lat": 39.7, "lng": -104.9},
        )
        assert resp.status_code == 422


# ── Test: GET /pantries/discover/status/{job_id} ────────────────────────────


class TestGetDiscoveryStatus:
    @pytest.fixture(autouse=True)
    def _clear(self):
        clear_job_state()
        yield
        clear_job_state()

    @pytest.mark.asyncio
    async def test_unknown_job_returns_404(self, client, test_db):
        """Nonexistent job ID returns 404."""
        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.get_status = AsyncMock(return_value=None)
            mock_svc.return_value = svc

            resp = await client.get("/pantries/discover/status/nonexistent-id")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_job_status(self, client, test_db):
        """Returns current status for a known job."""
        job_status = DiscoveryJobStatus(
            job_id="real-job",
            status=DiscoveryStatus.COMPLETED,
            query="Denver",
            urls_found=5,
            urls_processed=5,
            urls_succeeded=3,
            urls_failed=2,
        )

        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.get_status = AsyncMock(return_value=job_status)
            mock_svc.return_value = svc

            resp = await client.get("/pantries/discover/status/real-job")

        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "real-job"
        assert data["status"] == "completed"
        assert data["urls_succeeded"] == 3
        assert data["urls_failed"] == 2


# ── Test: GET /pantries/discover/stream/{job_id} ────────────────────────────


class TestStreamDiscovery:
    @pytest.fixture(autouse=True)
    def _clear(self):
        clear_job_state()
        yield
        clear_job_state()

    @pytest.mark.asyncio
    async def test_unknown_job_returns_404(self, client, test_db):
        """Stream for nonexistent job returns 404."""
        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.get_status = AsyncMock(return_value=None)
            mock_svc.return_value = svc

            resp = await client.get("/pantries/discover/stream/nonexistent")

        assert resp.status_code == 404


# ── Test: Structured Logging ────────────────────────────────────────────────


class TestDiscoveryLogging:
    @pytest.fixture(autouse=True)
    def _clear(self):
        clear_job_state()
        import main
        main._discovery_rate.clear()
        yield
        clear_job_state()

    @pytest.mark.asyncio
    async def test_logs_job_started(self, client, test_db, caplog):
        """Discovery endpoint logs job creation with structured fields."""
        import logging

        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.count_fresh_pantries = AsyncMock(return_value=0)
            svc.start_job = AsyncMock(return_value=DiscoveryJobStatus(
                job_id="log-test-job",
                status=DiscoveryStatus.RUNNING,
                query="Denver",
            ))
            mock_svc.return_value = svc

            with caplog.at_level(logging.INFO, logger="equitable"):
                await client.post(
                    "/pantries/discover",
                    json=_discovery_request(),
                )

        messages = [r.message for r in caplog.records]
        assert any("job created" in m.lower() for m in messages)

    @pytest.mark.asyncio
    async def test_logs_rate_limit(self, client, test_db, caplog):
        """Rate limit event is logged with structured fields."""
        import logging

        with patch("main._get_discovery_service") as mock_svc:
            svc = MagicMock()
            svc.count_fresh_pantries = AsyncMock(return_value=0)
            svc.start_job = AsyncMock(return_value=DiscoveryJobStatus(
                job_id="x",
                status=DiscoveryStatus.RUNNING,
                query="test",
            ))
            mock_svc.return_value = svc

            # Exhaust rate limit
            for _ in range(10):
                await client.post(
                    "/pantries/discover",
                    json=_discovery_request(),
                )

            with caplog.at_level(logging.WARNING, logger="equitable"):
                await client.post(
                    "/pantries/discover",
                    json=_discovery_request(),
                )

        messages = [r.message for r in caplog.records]
        assert any("rate limit" in m.lower() for m in messages)


# ── Test: Existing endpoints still work ──────────────────────────────────────


class TestExistingEndpoints:
    """Smoke test that discovery additions don't break existing routes."""

    @pytest.mark.asyncio
    async def test_health_check_still_works(self, client, test_db):
        resp = await client.get("/")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_pantries_still_works(self, client, test_db):
        resp = await client.get("/pantries")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_get_cities_still_works(self, client, test_db):
        resp = await client.get("/cities")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_nearby_still_works(self, client, test_db):
        resp = await client.get(
            "/pantries/nearby",
            params={"lat": 33.749, "lng": -84.388},
        )
        assert resp.status_code == 200
