"""
Smoke tests — these must pass before any merge.
They verify core functionality is not broken.

Tests run against the current API shape:
- GET / → {"message": "EquiTable API is running"}
- GET /api/test → {"status": "connected", "agent": "EquiTable v1"}
- GET /pantries → list[Pantry]
- GET /pantries/nearby?lat=&lng= → list[Pantry]
"""

import pytest


@pytest.mark.asyncio
class TestSmoke:
    async def test_health_check(self, client):
        """GET / returns 200 with a running message."""
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "running" in data["message"].lower()

    async def test_api_test_endpoint(self, client):
        """GET /api/test returns connected status."""
        response = await client.get("/api/test")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert "agent" in data

    async def test_get_pantries_returns_list(self, client, test_db, sample_pantry):
        """GET /pantries returns a list with inserted pantry."""
        await test_db.pantries.insert_one(sample_pantry)
        response = await client.get("/pantries")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_get_pantries_empty_db(self, client):
        """GET /pantries returns empty list when no data."""
        response = await client.get("/pantries")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    async def test_nearby_returns_geospatial_results(self, client, test_db, sample_pantry):
        """GET /pantries/nearby returns pantries within distance."""
        await test_db.pantries.insert_one(sample_pantry)
        response = await client.get(
            "/pantries/nearby",
            params={"lat": 33.749, "lng": -84.388, "max_distance": 16000},
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_nearby_invalid_coordinates_returns_422(self, client):
        """GET /pantries/nearby with non-numeric lat returns 422."""
        response = await client.get(
            "/pantries/nearby",
            params={"lat": "not_a_number", "lng": -84.0},
        )
        assert response.status_code == 422

    async def test_nearby_missing_params_returns_422(self, client):
        """GET /pantries/nearby without required params returns 422."""
        response = await client.get("/pantries/nearby")
        assert response.status_code == 422

    async def test_pantry_has_required_fields(self, client, test_db, sample_pantry):
        """Pantry response includes all required fields."""
        await test_db.pantries.insert_one(sample_pantry)
        response = await client.get("/pantries")
        pantry = response.json()[0]
        required_fields = ["name", "address", "lat", "lng", "status", "hours_notes"]
        for field in required_fields:
            assert field in pantry, f"Missing required field: {field}"

    async def test_confidence_in_valid_range(self, client, test_db, sample_pantry):
        """Confidence scores must be 1-10 when present."""
        await test_db.pantries.insert_one(sample_pantry)
        response = await client.get("/pantries")
        for pantry in response.json():
            if pantry.get("confidence") is not None:
                assert 1 <= pantry["confidence"] <= 10
