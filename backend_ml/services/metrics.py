"""Prometheus metrics for the scraper and the refresh agent (ADR-030).

Two processes run the same ScraperService, and they need opposite collection
models:

  API (long-lived Deployment)   PULL. Prometheus scrapes `/metrics` on a
                                dedicated port (METRICS_PORT) that the Ingress
                                never routes to, so the numbers are not public.
  Refresh agent (CronJob)       PUSH. The pod lives for minutes, fortnightly;
                                a 30s scrape interval would usually miss it
                                entirely. It pushes once, at the end of the
                                run, to a Pushgateway.

Everything is registered on a project-owned registry rather than the
prometheus_client global default, so tests can read values without process
collectors leaking in, and so the agent pushes only project metrics.

Metrics are strictly observational: no function here may raise into the
scraper or the refresh run. A broken Pushgateway must never fail a crawl.
"""

import logging
import os
import threading
import time
from typing import Iterable, Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)
from prometheus_client import REGISTRY as DEFAULT_REGISTRY
from prometheus_client import push_to_gateway

logger = logging.getLogger("equitable")

REGISTRY = CollectorRegistry(auto_describe=True)

# ── Scraper ──────────────────────────────────────────────────────────────────
#
# attempts vs results is the distinction the résumé number depends on:
#
#   attempts  one increment per tool TRIED. A Jina attempt only exists because
#             Crawl4AI came back short, so jina_attempts / crawl4ai_attempts is
#             the fallback rate.
#   results   one increment per URL, labelled with the tool that WON (or
#             "none"). This is the split: what fraction of pages each tool
#             actually delivered.
#
# Outcomes are derived from the return value only, so instrumentation cannot
# change control flow:
#   success       content >= MIN_CONTENT_CHARS
#   insufficient  some content, but under the threshold
#   failed        None / empty (fetch error, timeout, or blank page)

SCRAPE_ATTEMPTS = Counter(
    "equitable_scrape_attempts",
    "Scrape attempts per tool, by outcome.",
    ["method", "outcome"],
    registry=REGISTRY,
)

SCRAPE_RESULTS = Counter(
    "equitable_scrape_results",
    "URLs scraped, labelled by the tool that produced the content used.",
    ["method"],
    registry=REGISTRY,
)

SCRAPE_DURATION = Histogram(
    "equitable_scrape_duration_seconds",
    "Wall-clock time of one scrape attempt, per tool.",
    ["method"],
    # Crawl4AI's deep crawl routinely takes 10-20s; Jina retries with backoff
    # can push past a minute. Default buckets top out at 10s and would lump
    # every deep crawl into +Inf.
    buckets=(0.5, 1, 2.5, 5, 10, 20, 30, 60, 120, 300),
    registry=REGISTRY,
)


def classify(content: Optional[str], min_chars: int) -> str:
    if not content or not content.strip():
        return "failed"
    if len(content.strip()) < min_chars:
        return "insufficient"
    return "success"


def record_attempt(method: str, content: Optional[str], min_chars: int, seconds: float) -> None:
    try:
        SCRAPE_ATTEMPTS.labels(method=method, outcome=classify(content, min_chars)).inc()
        SCRAPE_DURATION.labels(method=method).observe(seconds)
    except Exception:  # metrics must never break a scrape
        logger.warning("Failed to record scrape metric", exc_info=True)


def record_result(method: str) -> None:
    try:
        SCRAPE_RESULTS.labels(method=method).inc()
    except Exception:
        logger.warning("Failed to record scrape metric", exc_info=True)


# ── API: pull ────────────────────────────────────────────────────────────────

METRICS_PORT_ENV_VAR = "METRICS_PORT"
_server_lock = threading.Lock()
_server_started = False


class _Proxy:
    """A collector that yields everything from several registries."""

    def __init__(self, registries: Iterable):
        self._registries = list(registries)

    def collect(self):
        for registry in self._registries:
            yield from registry.collect()

    def describe(self):
        # The registry indexes collectors by the names describe() returns;
        # without it, `?name[]=` filtering finds nothing to serve.
        return list(self.collect())


def _merged(*registries) -> CollectorRegistry:
    """One real registry exposing several. A real CollectorRegistry (rather than
    a bare object with collect()) keeps `/metrics?name[]=...` filtering working,
    which calls restricted_registry()."""
    merged = CollectorRegistry()
    merged.register(_Proxy(registries))
    return merged


def start_metrics_server_from_env() -> Optional[int]:
    """Serve /metrics on METRICS_PORT if it is set; otherwise do nothing.

    Off by default so local `uvicorn`, the test suite and the Render
    deployment are unchanged. Kubernetes sets the variable.

    A separate port (not a FastAPI route) because the Ingress forwards every
    path on the http port: a `/metrics` route would be public. On its own port
    it is reachable only from inside the cluster, and the NetworkPolicy narrows
    that to the monitoring namespace.

    Includes the default registry for process_* (RSS, CPU, open fds) and
    python_gc_* — useful next to the 2Gi limit, where Chromium makes memory the
    thing that goes wrong.
    """
    global _server_started
    raw = os.getenv(METRICS_PORT_ENV_VAR, "").strip()
    if not raw:
        return None
    port = int(raw)
    with _server_lock:
        if _server_started:
            return port
        start_http_server(port, registry=_merged(REGISTRY, DEFAULT_REGISTRY))
        _server_started = True
    logger.info("Metrics server listening", extra={"event": "metrics_server_start", "port": port})
    return port


# ── Refresh agent: push ──────────────────────────────────────────────────────

PUSHGATEWAY_ENV_VAR = "PUSHGATEWAY_URL"
PUSH_JOB = "equitable_refresh"


def build_refresh_registry(final: dict, duration_seconds: float) -> CollectorRegistry:
    """Run-level gauges, built fresh per push so they describe exactly one run."""
    reg = CollectorRegistry()
    sources = Gauge("equitable_refresh_sources",
                    "Sources processed in this refresh run, by outcome.",
                    ["outcome"], registry=reg)
    results = final.get("results", []) or []
    for outcome in ("success", "failed", "skipped_budget"):
        sources.labels(outcome=outcome).set(
            sum(1 for r in results if r.get("outcome") == outcome))

    Gauge("equitable_refresh_cost_usd",
          "Gemini spend for this refresh run (USD).",
          registry=reg).set(float(final.get("cost_spent_usd", 0.0) or 0.0))
    Gauge("equitable_refresh_duration_seconds",
          "Wall-clock duration of this refresh process.",
          registry=reg).set(duration_seconds)
    Gauge("equitable_refresh_last_completion_timestamp_seconds",
          "Unix time this refresh run finished.",
          registry=reg).set(time.time())
    return reg


def push_refresh_metrics(run_id: str, final: dict, duration_seconds: float,
                         gateway: Optional[str] = None) -> bool:
    """Push scraper counters + run gauges to the Pushgateway. Never raises.

    Grouped by run_id, so each fortnightly run is its own group and
    `sum by (method) (equitable_scrape_results_total{job="equitable_refresh"})`
    is the cumulative split across every run the gateway still holds. Pushing
    with a constant grouping key would instead overwrite the previous run.

    A crash-and-resume shares one run_id (the Job name): the resumed pod's
    push replaces the group. The crashed pod never pushed, so its attempts are
    not counted — the durable per-pantry record stays `scrape_method` in Mongo.

    Returns True if pushed, False if disabled or the push failed.
    """
    gateway = gateway if gateway is not None else os.getenv(PUSHGATEWAY_ENV_VAR, "").strip()
    if not gateway:
        return False
    try:
        registry = _merged(REGISTRY, build_refresh_registry(final, duration_seconds))
        push_to_gateway(gateway, job=PUSH_JOB, grouping_key={"run_id": run_id},
                        registry=registry, timeout=5)
        logger.info("Pushed refresh metrics",
                    extra={"event": "metrics_pushed", "run_id": run_id, "gateway": gateway})
        return True
    except Exception as e:
        logger.warning("Metrics push failed; run result unaffected",
                       extra={"event": "metrics_push_failed", "run_id": run_id, "error": str(e)})
        return False
