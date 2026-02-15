"""
Tests for the multi-city seed script logic.
Tests load/filter functions and upsert/freshness behavior against the test DB.
"""

import json
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

import pytest

# Import from scripts — need path manipulation since scripts/ isn't a package
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.seed_cities import load_seed_data, filter_cities


class TestLoadSeedData:
    """Tests for seed data loading."""

    def test_load_seed_data_returns_list(self):
        """load_seed_data returns a list of city dicts."""
        cities = load_seed_data()
        assert isinstance(cities, list)
        assert len(cities) > 0

    def test_seed_data_has_required_fields(self):
        """Each city entry has required fields."""
        cities = load_seed_data()
        for city in cities:
            assert "city" in city
            assert "state" in city
            assert "tier" in city
            assert "center" in city
            assert "pantries" in city
            assert len(city["pantries"]) > 0

    def test_seed_data_pantry_fields(self):
        """Each pantry entry has required fields."""
        cities = load_seed_data()
        for city in cities:
            for p in city["pantries"]:
                assert "name" in p
                assert "url" in p
                assert "address" in p
                assert "lat" in p
                assert "lng" in p


class TestFilterCities:
    """Tests for city filtering logic."""

    def test_filter_by_city_name(self):
        cities = load_seed_data()
        result = filter_cities(cities, "Atlanta", None)
        assert len(result) == 1
        assert result[0]["city"] == "Atlanta"

    def test_filter_by_city_name_case_insensitive(self):
        cities = load_seed_data()
        result = filter_cities(cities, "atlanta", None)
        assert len(result) == 1
        assert result[0]["city"] == "Atlanta"

    def test_filter_by_tier(self):
        cities = load_seed_data()
        result = filter_cities(cities, None, 1)
        assert len(result) == 5  # All Tier 1 cities

    def test_filter_no_match(self):
        cities = load_seed_data()
        result = filter_cities(cities, "Nonexistent", None)
        assert len(result) == 0

    def test_no_filter_returns_all(self):
        cities = load_seed_data()
        result = filter_cities(cities, None, None)
        assert len(result) == len(cities)


class TestUpsertBehavior:
    """Tests for upsert and freshness logic against the test DB."""

    async def test_upsert_creates_new_document(self, test_db):
        """Upserting by source_url creates a new doc when none exists."""
        pantries = test_db["pantries"]

        doc = {
            "name": "Test Pantry",
            "address": "123 Test St",
            "lat": 33.749,
            "lng": -84.388,
            "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
            "hours_notes": "Mon-Fri 9-5",
            "city": "Atlanta",
            "state": "GA",
            "source_url": "https://upsert-test.example.com",
            "last_updated": datetime.now(timezone.utc),
        }

        result = await pantries.update_one(
            {"source_url": "https://upsert-test.example.com"},
            {"$set": doc},
            upsert=True,
        )
        assert result.upserted_id is not None

        count = await pantries.count_documents({"source_url": "https://upsert-test.example.com"})
        assert count == 1

    async def test_upsert_updates_existing_document(self, test_db):
        """Re-upserting same source_url updates the existing doc instead of duplicating."""
        pantries = test_db["pantries"]

        doc = {
            "name": "Original Name",
            "address": "123 Test St",
            "lat": 33.749,
            "lng": -84.388,
            "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
            "hours_notes": "Mon-Fri 9-5",
            "city": "Atlanta",
            "state": "GA",
            "source_url": "https://upsert-dedup.example.com",
            "last_updated": datetime.now(timezone.utc),
        }

        await pantries.update_one(
            {"source_url": "https://upsert-dedup.example.com"},
            {"$set": doc},
            upsert=True,
        )

        # Update with new name
        doc["name"] = "Updated Name"
        await pantries.update_one(
            {"source_url": "https://upsert-dedup.example.com"},
            {"$set": doc},
            upsert=True,
        )

        count = await pantries.count_documents({"source_url": "https://upsert-dedup.example.com"})
        assert count == 1

        result = await pantries.find_one({"source_url": "https://upsert-dedup.example.com"})
        assert result["name"] == "Updated Name"

    async def test_freshness_skip_logic(self, test_db):
        """Documents updated < 24h ago should be detected as fresh."""
        pantries = test_db["pantries"]

        recent_time = datetime.now(timezone.utc) - timedelta(hours=2)
        await pantries.insert_one({
            "name": "Fresh Pantry",
            "address": "123 Test St",
            "lat": 33.749,
            "lng": -84.388,
            "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
            "hours_notes": "Mon-Fri 9-5",
            "city": "Atlanta",
            "state": "GA",
            "source_url": "https://freshness-test.example.com",
            "last_updated": recent_time,
        })

        existing = await pantries.find_one({"source_url": "https://freshness-test.example.com"})
        last_updated = existing["last_updated"]
        if not last_updated.tzinfo:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - last_updated

        assert age < timedelta(hours=24), "Should be detected as fresh (< 24h)"

    async def test_stale_document_detected(self, test_db):
        """Documents updated > 24h ago should be detected as stale."""
        pantries = test_db["pantries"]

        old_time = datetime.now(timezone.utc) - timedelta(hours=48)
        await pantries.insert_one({
            "name": "Stale Pantry",
            "address": "123 Test St",
            "lat": 33.749,
            "lng": -84.388,
            "location": {"type": "Point", "coordinates": [-84.388, 33.749]},
            "hours_notes": "Mon-Fri 9-5",
            "city": "Atlanta",
            "state": "GA",
            "source_url": "https://stale-test.example.com",
            "last_updated": old_time,
        })

        existing = await pantries.find_one({"source_url": "https://stale-test.example.com"})
        last_updated = existing["last_updated"]
        if not last_updated.tzinfo:
            last_updated = last_updated.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - last_updated

        assert age >= timedelta(hours=24), "Should be detected as stale (> 24h)"
