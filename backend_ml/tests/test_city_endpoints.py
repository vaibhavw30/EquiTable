"""
Tests for multi-city API endpoints:
- GET /pantries with city/state filters
- GET /cities aggregation endpoint
- POST /pantries/{id}/ingest with city/state
"""

from datetime import datetime, timezone


class TestGetPantriesCityFilter:
    """Tests for GET /pantries with city/state query params."""

    async def test_no_filter_returns_all(self, client, test_db):
        """GET /pantries with no params returns all pantries (backward compat)."""
        await test_db["pantries"].insert_many([
            {
                "name": "ATL Pantry", "address": "123 Peachtree St",
                "lat": 33.749, "lng": -84.388,
                "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
                "hours_notes": "Mon-Fri 9-5", "city": "Atlanta", "state": "GA",
                "source_url": "https://atl.example.com",
            },
            {
                "name": "NYC Pantry", "address": "456 Broadway",
                "lat": 40.7128, "lng": -74.006,
                "location": {"type": "Point", "coordinates": [-74.006, 40.7128]},
                "hours_notes": "Mon-Fri 9-5", "city": "New York City", "state": "NY",
                "source_url": "https://nyc.example.com",
            },
        ])

        resp = await client.get("/pantries")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_filter_by_city(self, client, test_db):
        """GET /pantries?city=Atlanta returns only Atlanta pantries."""
        await test_db["pantries"].insert_many([
            {
                "name": "ATL Pantry", "address": "123 Peachtree St",
                "lat": 33.749, "lng": -84.388,
                "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
                "hours_notes": "Mon-Fri 9-5", "city": "Atlanta", "state": "GA",
                "source_url": "https://atl.example.com",
            },
            {
                "name": "NYC Pantry", "address": "456 Broadway",
                "lat": 40.7128, "lng": -74.006,
                "location": {"type": "Point", "coordinates": [-74.006, 40.7128]},
                "hours_notes": "Mon-Fri 9-5", "city": "New York City", "state": "NY",
                "source_url": "https://nyc.example.com",
            },
        ])

        resp = await client.get("/pantries", params={"city": "Atlanta"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "ATL Pantry"

    async def test_filter_case_insensitive(self, client, test_db):
        """City filtering is case-insensitive."""
        await test_db["pantries"].insert_one({
            "name": "ATL Pantry", "address": "123 Peachtree St",
            "lat": 33.749, "lng": -84.388,
            "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
            "hours_notes": "Mon-Fri 9-5", "city": "Atlanta", "state": "GA",
            "source_url": "https://atl2.example.com",
        })

        resp = await client.get("/pantries", params={"city": "atlanta"})
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    async def test_filter_by_state(self, client, test_db):
        """GET /pantries?state=NY returns only NY pantries."""
        await test_db["pantries"].insert_many([
            {
                "name": "ATL Pantry", "address": "123 Peachtree St",
                "lat": 33.749, "lng": -84.388,
                "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
                "hours_notes": "Mon-Fri 9-5", "city": "Atlanta", "state": "GA",
                "source_url": "https://atl3.example.com",
            },
            {
                "name": "NYC Pantry", "address": "456 Broadway",
                "lat": 40.7128, "lng": -74.006,
                "location": {"type": "Point", "coordinates": [-74.006, 40.7128]},
                "hours_notes": "Mon-Fri 9-5", "city": "New York City", "state": "NY",
                "source_url": "https://nyc2.example.com",
            },
        ])

        resp = await client.get("/pantries", params={"state": "NY"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["city"] == "New York City"

    async def test_filter_no_results(self, client, test_db):
        """Filter with non-existent city returns empty list."""
        await test_db["pantries"].insert_one({
            "name": "ATL Pantry", "address": "123 Peachtree St",
            "lat": 33.749, "lng": -84.388,
            "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
            "hours_notes": "Mon-Fri 9-5", "city": "Atlanta", "state": "GA",
            "source_url": "https://atl4.example.com",
        })

        resp = await client.get("/pantries", params={"city": "Denver"})
        assert resp.status_code == 200
        assert len(resp.json()) == 0


class TestGetCities:
    """Tests for GET /cities endpoint."""

    async def test_returns_city_list_with_counts(self, client, test_db):
        """GET /cities returns aggregated city list with counts and centers."""
        await test_db["pantries"].insert_many([
            {
                "name": "ATL 1", "address": "a", "lat": 33.749, "lng": -84.388,
                "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
                "hours_notes": "h", "city": "Atlanta", "state": "GA",
                "source_url": "https://atl-c1.example.com",
            },
            {
                "name": "ATL 2", "address": "b", "lat": 33.75, "lng": -84.39,
                "location": {"type": "Point", "coordinates": [-84.39, 33.75]},
                "hours_notes": "h", "city": "Atlanta", "state": "GA",
                "source_url": "https://atl-c2.example.com",
            },
            {
                "name": "NYC 1", "address": "c", "lat": 40.71, "lng": -74.006,
                "location": {"type": "Point", "coordinates": [-74.006, 40.71]},
                "hours_notes": "h", "city": "New York City", "state": "NY",
                "source_url": "https://nyc-c1.example.com",
            },
        ])

        resp = await client.get("/cities")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        # Atlanta has 2 pantries, NYC has 1 — sorted by count desc
        assert data[0]["city"] == "Atlanta"
        assert data[0]["count"] == 2
        assert data[0]["center"]["lat"] == 33.749

        assert data[1]["city"] == "New York City"
        assert data[1]["count"] == 1

    async def test_excludes_null_city(self, client, test_db):
        """Pantries without city field are not included in /cities."""
        await test_db["pantries"].insert_many([
            {
                "name": "ATL 1", "address": "a", "lat": 33.749, "lng": -84.388,
                "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
                "hours_notes": "h", "city": "Atlanta", "state": "GA",
                "source_url": "https://atl-c3.example.com",
            },
            {
                "name": "No City", "address": "b", "lat": 33.75, "lng": -84.39,
                "location": {"type": "Point", "coordinates": [-84.39, 33.75]},
                "hours_notes": "h",
                "source_url": "https://nocity.example.com",
            },
        ])

        resp = await client.get("/cities")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["city"] == "Atlanta"

    async def test_empty_db(self, client, test_db):
        """GET /cities on empty DB returns empty list."""
        resp = await client.get("/cities")
        assert resp.status_code == 200
        assert resp.json() == []
