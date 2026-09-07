"""Kubernetes liveness/readiness probe tests.

The point of these probes is that they FAIL when they should. A readiness
probe that returns 200 while MongoDB is unreachable is worse than no probe:
kubelet keeps the pod in the Service endpoints and every request 500s.

So the important cases here are the negative ones — Mongo missing, Mongo
erroring, Mongo hanging — each of which must produce a 503.
"""

import asyncio

import pytest

import database


class _FakeAdmin:
    """Stands in for `motor_client.admin`, with a scriptable `command`."""

    def __init__(self, behavior):
        self._behavior = behavior

    async def command(self, name):
        assert name == "ping"
        return await self._behavior()


class _FakeClient:
    def __init__(self, behavior):
        self.admin = _FakeAdmin(behavior)


class _FakeDb:
    """Minimal stand-in for a Motor database: only `.client` is needed."""

    def __init__(self, behavior):
        self.client = _FakeClient(behavior)


@pytest.mark.asyncio
class TestLivenessProbe:
    async def test_liveness_returns_alive(self, client):
        """GET /healthz/live returns 200 without touching any dependency."""
        response = await client.get("/healthz/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    async def test_liveness_stays_up_when_mongo_is_down(self, client, monkeypatch):
        """Liveness must NOT fail on a Mongo outage.

        This is the whole liveness/readiness split. If liveness checked Mongo,
        an Atlas outage would restart every pod on a loop — turning a
        recoverable dependency failure into a cluster-wide CrashLoopBackOff.
        """
        monkeypatch.setattr(database, "db", None)

        response = await client.get("/healthz/live")
        assert response.status_code == 200, (
            "liveness probe checked a dependency it must not check"
        )


@pytest.mark.asyncio
class TestReadinessProbe:
    async def test_ready_when_mongo_reachable(self, client, test_db):
        """GET /healthz/ready returns 200 against a live Atlas connection."""
        response = await client.get("/healthz/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["dependency"] == "mongodb"
        assert isinstance(body["latency_ms"], (int, float))
        assert body["latency_ms"] >= 0

    async def test_unready_when_db_handle_missing(self, client, monkeypatch):
        """No database handle → 503, not a 200 and not a 500."""
        monkeypatch.setattr(database, "db", None)

        response = await client.get("/healthz/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unready"
        assert body["dependency"] == "mongodb"
        assert "not initialised" in body["error"]

    async def test_unready_when_ping_errors(self, client, monkeypatch):
        """A refused/failed Mongo connection surfaces as 503 with the reason.

        This is the 'break Mongo access and watch the probe fail' case, run
        deterministically instead of by actually severing the network.
        """
        async def refuse():
            raise ConnectionRefusedError("connection refused by replica set")

        monkeypatch.setattr(database, "db", _FakeDb(refuse))

        response = await client.get("/healthz/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unready"
        assert "connection refused" in body["error"]

    async def test_unready_when_ping_hangs_past_timeout(self, client, monkeypatch):
        """A hanging Mongo must time out into a 503, not hang the probe.

        An unbounded probe never reports unready, so kubelet would keep routing
        traffic to a pod that cannot serve. The timeout is what converts a hang
        into a definite failure.
        """
        async def hang():
            await asyncio.sleep(30)

        monkeypatch.setattr(database, "db", _FakeDb(hang))
        monkeypatch.setattr("main.READINESS_PING_TIMEOUT_SECONDS", 0.05)

        response = await asyncio.wait_for(client.get("/healthz/ready"), timeout=5)
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unready"
        assert "budget" in body["error"], f"expected a timeout reason, got {body['error']!r}"

    async def test_readiness_recovers_after_outage(self, client, test_db, monkeypatch):
        """Readiness flips back to 200 once Mongo returns — no restart needed.

        Proves the probe is level-triggered on current state rather than
        latching a failure, which is why a Mongo blip does not need a pod kill.
        """
        async def refuse():
            raise ConnectionRefusedError("down")

        monkeypatch.setattr(database, "db", _FakeDb(refuse))
        assert (await client.get("/healthz/ready")).status_code == 503

        monkeypatch.setattr(database, "db", test_db)
        assert (await client.get("/healthz/ready")).status_code == 200
