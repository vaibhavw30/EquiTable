"""
Tests for PlacesClient — Google Places API wrapper.

Covers single search, multi-query search, Place Details fallback, and caching.
All tests use mocked httpx — no live API calls.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from services.places_client import PlacesClient, PlacesAPIError


def _mock_places_response(places: list) -> dict:
    """Build a mock Places API JSON response."""
    return {"places": places}


def _make_place(
    name="Test Food Bank",
    address="123 Main St, Denver, CO 80202, USA",
    lat=39.7392,
    lng=-104.9903,
    website_uri="https://testfoodbank.org",
    place_id="place_abc123",
):
    """Build a single place object matching the Places API shape."""
    place = {
        "displayName": {"text": name},
        "formattedAddress": address,
        "location": {"latitude": lat, "longitude": lng},
        "id": place_id,
    }
    if website_uri:
        place["websiteUri"] = website_uri
    return place


def _make_mock_httpx_client(response):
    """Create a mock httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    mock_client.post.return_value = response
    mock_client.get.return_value = response
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestSearchNearby:
    """Tests for backward-compatible single-query search_nearby."""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _mock_places_response([
            _make_place(name="Denver Rescue Mission", website_uri="https://denverrescue.org"),
            _make_place(name="Food Bank of the Rockies", website_uri="https://foodbankrockies.org"),
        ])

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value = _make_mock_httpx_client(mock_response)
            MockClient.return_value.post.return_value = mock_response

            client = PlacesClient(api_key="test-key")
            results = await client.search_nearby("Denver, CO", 39.7392, -104.9903)

        assert len(results) == 2
        assert results[0].name == "Denver Rescue Mission"
        assert results[0].website_url == "https://denverrescue.org"

    @pytest.mark.asyncio
    async def test_search_handles_no_results(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _mock_places_response([])

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value = _make_mock_httpx_client(mock_response)
            MockClient.return_value.post.return_value = mock_response

            client = PlacesClient(api_key="test-key")
            results = await client.search_nearby("Middle of Nowhere", 0, 0)

        assert results == []

    @pytest.mark.asyncio
    async def test_search_handles_missing_website(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _mock_places_response([
            _make_place(name="Church Pantry", website_uri=None),
        ])

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value = _make_mock_httpx_client(mock_response)
            MockClient.return_value.post.return_value = mock_response

            client = PlacesClient(api_key="test-key")
            results = await client.search_nearby("Denver, CO", 39.7, -104.9)

        assert len(results) == 1
        assert results[0].website_url is None

    @pytest.mark.asyncio
    async def test_search_respects_max_results(self):
        places = [_make_place(name=f"Pantry {i}", place_id=f"id_{i}") for i in range(15)]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _mock_places_response(places)

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value = _make_mock_httpx_client(mock_response)
            MockClient.return_value.post.return_value = mock_response

            client = PlacesClient(api_key="test-key")
            results = await client.search_nearby("Denver", 39.7, -104.9, max_results=5)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_search_raises_on_api_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "API key invalid"

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            MockClient.return_value = _make_mock_httpx_client(mock_response)
            MockClient.return_value.post.return_value = mock_response

            client = PlacesClient(api_key="bad-key")

            with pytest.raises(PlacesAPIError) as exc_info:
                await client.search_nearby("Denver", 39.7, -104.9)

            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_search_sends_correct_request(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _mock_places_response([])

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            mock_client = _make_mock_httpx_client(mock_response)
            mock_client.post.return_value = mock_response
            MockClient.return_value = mock_client

            client = PlacesClient(api_key="test-key")
            await client.search_nearby("Denver, CO", 39.7392, -104.9903, radius_meters=5000)

        call_args = mock_client.post.call_args
        body = call_args.kwargs.get("json") or call_args[1].get("json")
        assert "food pantry OR food bank" in body["textQuery"]
        assert body["locationBias"]["circle"]["center"]["latitude"] == 39.7392

        headers = call_args.kwargs.get("headers") or call_args[1].get("headers")
        assert headers["X-Goog-Api-Key"] == "test-key"
        assert "websiteUri" in headers["X-Goog-FieldMask"]


class TestSearchMultiQuery:
    """Tests for multi-query search with dedup and caching."""

    @pytest.mark.asyncio
    async def test_multi_query_deduplicates_by_place_id(self):
        """Same place_id across queries is only returned once."""
        place_a = _make_place(name="Food Bank A", place_id="id_A")
        place_b = _make_place(name="Pantry B", place_id="id_B")
        # Duplicate of A from different query
        place_a_dup = _make_place(name="Food Bank A", place_id="id_A")

        call_count = 0

        def make_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if call_count == 1:
                mock_resp.json.return_value = _mock_places_response([place_a, place_b])
            elif call_count == 2:
                mock_resp.json.return_value = _mock_places_response([place_a_dup])
            else:
                mock_resp.json.return_value = _mock_places_response([])
            return mock_resp

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.side_effect = make_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            # Use db=None to skip cache (no collection available)
            client = PlacesClient(api_key="test-key", db=None)
            # Patch cache methods to be no-ops
            client._check_cache = AsyncMock(return_value=None)
            client._store_cache = AsyncMock()

            results = await client.search_multi_query(39.7, -104.9)

        assert len(results) == 2
        place_ids = {r.place_id for r in results}
        assert place_ids == {"id_A", "id_B"}

    @pytest.mark.asyncio
    async def test_multi_query_runs_four_queries(self):
        """All 4 discovery queries are executed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _mock_places_response([])

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            client = PlacesClient(api_key="test-key", db=None)
            client._check_cache = AsyncMock(return_value=None)
            client._store_cache = AsyncMock()

            await client.search_multi_query(39.7, -104.9)

        # 4 queries = 4 API calls
        assert mock_client.post.call_count == 4

    @pytest.mark.asyncio
    async def test_multi_query_continues_on_partial_failure(self):
        """If one query fails, others still execute."""
        call_count = 0

        def make_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count == 2:
                mock_resp.status_code = 500
                mock_resp.text = "Server error"
            else:
                mock_resp.status_code = 200
                mock_resp.json.return_value = _mock_places_response([
                    _make_place(name=f"Place {call_count}", place_id=f"id_{call_count}")
                ])
            return mock_resp

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.side_effect = make_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            client = PlacesClient(api_key="test-key", db=None)
            client._check_cache = AsyncMock(return_value=None)
            client._store_cache = AsyncMock()

            results = await client.search_multi_query(39.7, -104.9)

        # 3 out of 4 queries succeeded, each returning 1 result
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_cache_hit_skips_api_calls(self):
        """Cached results are returned without making API calls."""
        from models.discovery import PlaceResult

        cached_results = [
            PlaceResult(name="Cached Bank", address="1 Main St", lat=39.7, lng=-104.9, website_url="https://cached.org", place_id="cached_1"),
        ]

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            MockClient.return_value = mock_client

            client = PlacesClient(api_key="test-key", db=None)
            client._check_cache = AsyncMock(return_value=cached_results)
            client._store_cache = AsyncMock()

            results = await client.search_multi_query(39.7, -104.9)

        assert len(results) == 1
        assert results[0].name == "Cached Bank"
        # No API calls made
        mock_client.post.assert_not_called()


class TestGetPlaceWebsite:
    """Tests for Place Details website fallback."""

    @pytest.mark.asyncio
    async def test_returns_website_url(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"websiteUri": "https://foodbank.org"}

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            mock_client = _make_mock_httpx_client(mock_response)
            mock_client.get.return_value = mock_response
            MockClient.return_value = mock_client

            client = PlacesClient(api_key="test-key")
            url = await client.get_place_website("place_123")

        assert url == "https://foodbank.org"

    @pytest.mark.asyncio
    async def test_returns_none_on_no_website(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            mock_client = _make_mock_httpx_client(mock_response)
            mock_client.get.return_value = mock_response
            MockClient.return_value = mock_client

            client = PlacesClient(api_key="test-key")
            url = await client.get_place_website("place_123")

        assert url is None

    @pytest.mark.asyncio
    async def test_returns_none_on_api_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"

        with patch("services.places_client.httpx.AsyncClient") as MockClient:
            mock_client = _make_mock_httpx_client(mock_response)
            mock_client.get.return_value = mock_response
            MockClient.return_value = mock_client

            client = PlacesClient(api_key="test-key")
            url = await client.get_place_website("bad_id")

        assert url is None
