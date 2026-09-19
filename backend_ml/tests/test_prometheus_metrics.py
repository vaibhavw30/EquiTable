"""Prometheus instrumentation (ADR-030).

Counters are process-global, so every assertion is a DELTA against a snapshot
taken before the action — never an absolute value.
"""

import socket
import urllib.request
from unittest.mock import patch

import pytest
from prometheus_client import generate_latest

from services import metrics
from services.scraper import MIN_CONTENT_CHARS, ScraperService

RICH = "r" * (MIN_CONTENT_CHARS + 50)
THIN = "t" * (MIN_CONTENT_CHARS - 10)


def _val(name, **labels):
    return metrics.REGISTRY.get_sample_value(name, labels) or 0.0


def attempts(method, outcome):
    return _val("equitable_scrape_attempts_total", method=method, outcome=outcome)


def results(method):
    return _val("equitable_scrape_results_total", method=method)


def durations(method):
    return _val("equitable_scrape_duration_seconds_count", method=method)


class _Fetcher:
    def __init__(self, name, result, enabled=True):
        self.name, self.result, self.enabled = name, result, enabled

    async def fetch(self, url):
        return self.result


def _svc(monkeypatch, primary, fallbacks):
    svc = ScraperService(fallback_fetchers=fallbacks)

    async def fake_primary(url):
        return primary

    monkeypatch.setattr(svc, "_crawl4ai_scrape", fake_primary)
    return svc


class Snapshot:
    """Capture the counters a scrape can touch, then report deltas."""

    KEYS = [("crawl4ai", o) for o in ("success", "insufficient", "failed")] + \
           [("jina", o) for o in ("success", "insufficient", "failed")]

    def __init__(self):
        self.a = {k: attempts(*k) for k in self.KEYS}
        self.r = {m: results(m) for m in ("crawl4ai", "jina", "none")}
        self.d = {m: durations(m) for m in ("crawl4ai", "jina")}

    def attempts(self):
        return {k: attempts(*k) - v for k, v in self.a.items() if attempts(*k) - v}

    def results(self):
        return {m: results(m) - v for m, v in self.r.items() if results(m) - v}

    def durations(self):
        return {m: durations(m) - v for m, v in self.d.items() if durations(m) - v}


# ── Scraper instrumentation ──────────────────────────────────────────────────

async def test_crawl4ai_success_records_one_attempt_and_the_win(monkeypatch):
    snap = Snapshot()
    res = await _svc(monkeypatch, RICH, [_Fetcher("jina", RICH)]).scrape_with_provenance("https://x.org")
    assert res.method == "crawl4ai"
    assert snap.attempts() == {("crawl4ai", "success"): 1}
    assert snap.results() == {"crawl4ai": 1}
    assert snap.durations() == {"crawl4ai": 1}


async def test_fallback_records_both_attempts_and_jina_win(monkeypatch):
    snap = Snapshot()
    res = await _svc(monkeypatch, "\n", [_Fetcher("jina", RICH)]).scrape_with_provenance("https://x.org")
    assert res.method == "jina"
    assert snap.attempts() == {("crawl4ai", "failed"): 1, ("jina", "success"): 1}
    assert snap.results() == {"jina": 1}
    assert snap.durations() == {"crawl4ai": 1, "jina": 1}


async def test_everything_failing_records_none(monkeypatch):
    snap = Snapshot()
    res = await _svc(monkeypatch, None, [_Fetcher("jina", None)]).scrape_with_provenance("https://x.org")
    assert res.method == "none"
    assert snap.attempts() == {("crawl4ai", "failed"): 1, ("jina", "failed"): 1}
    assert snap.results() == {"none": 1}


async def test_thin_crawl4ai_kept_is_counted_as_a_crawl4ai_result(monkeypatch):
    snap = Snapshot()
    res = await _svc(monkeypatch, THIN, [_Fetcher("jina", THIN)]).scrape_with_provenance("https://x.org")
    assert res.method == "crawl4ai" and res.content == THIN
    assert snap.attempts() == {("crawl4ai", "insufficient"): 1, ("jina", "insufficient"): 1}
    assert snap.results() == {"crawl4ai": 1}


async def test_disabled_fetcher_records_no_attempt(monkeypatch):
    snap = Snapshot()
    fallbacks = [_Fetcher("jina", RICH, enabled=False)]
    await _svc(monkeypatch, None, fallbacks).scrape_with_provenance("https://x.org")
    assert ("jina", "success") not in snap.attempts()
    assert snap.results() == {"none": 1}


async def test_scrape_url_wrapper_is_counted_too(monkeypatch):
    """The API's ingestion pipeline calls scrape_url, not scrape_with_provenance."""
    snap = Snapshot()
    assert await _svc(monkeypatch, RICH, []).scrape_url("https://x.org") == RICH
    assert snap.results() == {"crawl4ai": 1}


async def test_broken_metrics_never_break_a_scrape(monkeypatch):
    def boom(**_):
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(metrics.SCRAPE_ATTEMPTS, "labels", boom)
    monkeypatch.setattr(metrics.SCRAPE_RESULTS, "labels", boom)
    res = await _svc(monkeypatch, "\n", [_Fetcher("jina", RICH)]).scrape_with_provenance("https://x.org")
    assert res.method == "jina" and res.content == RICH


@pytest.mark.parametrize("content,expected", [
    (None, "failed"), ("", "failed"), ("   \n", "failed"),
    ("a" * (MIN_CONTENT_CHARS - 1), "insufficient"),
    ("a" * MIN_CONTENT_CHARS, "success"),
])
def test_classify_matches_the_fallback_threshold(content, expected):
    assert metrics.classify(content, MIN_CONTENT_CHARS) == expected


# ── Refresh agent push ───────────────────────────────────────────────────────

FINAL = {
    "results": [{"outcome": "success"}, {"outcome": "success"},
                {"outcome": "failed"}, {"outcome": "skipped_budget"}],
    "cost_spent_usd": 0.0123,
}


def test_push_is_a_noop_without_a_gateway(monkeypatch):
    monkeypatch.delenv(metrics.PUSHGATEWAY_ENV_VAR, raising=False)
    with patch.object(metrics, "push_to_gateway") as push:
        assert metrics.push_refresh_metrics("run-1", FINAL, 12.0) is False
    push.assert_not_called()


def test_push_groups_by_run_id_and_carries_scraper_and_run_metrics(monkeypatch):
    monkeypatch.setenv(metrics.PUSHGATEWAY_ENV_VAR, "pushgw.monitoring:9091")
    metrics.record_result("jina")  # ensure at least one scraper series exists
    with patch.object(metrics, "push_to_gateway") as push:
        assert metrics.push_refresh_metrics("equitable-refresh-29301234", FINAL, 42.5) is True

    args, kwargs = push.call_args
    assert args[0] == "pushgw.monitoring:9091"
    assert kwargs["job"] == "equitable_refresh"
    assert kwargs["grouping_key"] == {"run_id": "equitable-refresh-29301234"}
    body = generate_latest(kwargs["registry"]).decode()
    assert 'equitable_scrape_results_total{method="jina"}' in body
    assert 'equitable_refresh_sources{outcome="success"} 2.0' in body
    assert 'equitable_refresh_sources{outcome="failed"} 1.0' in body
    assert 'equitable_refresh_sources{outcome="skipped_budget"} 1.0' in body
    assert "equitable_refresh_cost_usd 0.0123" in body
    assert "equitable_refresh_duration_seconds 42.5" in body
    assert "equitable_refresh_last_completion_timestamp_seconds" in body
    # Default-registry metrics describe the pusher process, not the run.
    assert "python_info" not in body


def test_push_failure_is_swallowed(monkeypatch):
    with patch.object(metrics, "push_to_gateway", side_effect=OSError("connection refused")):
        assert metrics.push_refresh_metrics("run-1", FINAL, 1.0, gateway="nowhere:9091") is False


def test_refresh_registry_handles_an_empty_run():
    body = generate_latest(metrics.build_refresh_registry({}, 0.0)).decode()
    assert 'equitable_refresh_sources{outcome="success"} 0.0' in body
    assert "equitable_refresh_cost_usd 0.0" in body


# ── API metrics endpoint ─────────────────────────────────────────────────────

@pytest.fixture
def fresh_server_state(monkeypatch):
    monkeypatch.setattr(metrics, "_server_started", False)


def test_metrics_server_is_off_by_default(monkeypatch, fresh_server_state):
    monkeypatch.delenv(metrics.METRICS_PORT_ENV_VAR, raising=False)
    with patch.object(metrics, "start_http_server") as start:
        assert metrics.start_metrics_server_from_env() is None
    start.assert_not_called()


def test_metrics_server_serves_project_and_process_metrics(monkeypatch, fresh_server_state):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setenv(metrics.METRICS_PORT_ENV_VAR, str(port))
    metrics.record_result("crawl4ai")

    assert metrics.start_metrics_server_from_env() == port
    # Idempotent: a second call (e.g. lifespan re-entry) must not rebind.
    assert metrics.start_metrics_server_from_env() == port

    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=5).read().decode()
    assert 'equitable_scrape_results_total{method="crawl4ai"}' in body
    # From the default registry. (process_* is there too on Linux; macOS has no
    # /proc, so the process collector is empty when this runs locally.)
    assert "python_info" in body

    # name[] filtering needs a real registry underneath, not a duck-typed one.
    only = urllib.request.urlopen(
        f"http://127.0.0.1:{port}/metrics?name[]=equitable_scrape_results_total", timeout=5
    ).read().decode()
    assert "equitable_scrape_results_total" in only
    assert "python_info" not in only
