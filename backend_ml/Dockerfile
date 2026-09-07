# backend_ml/Dockerfile
#
# Two images from one file, sharing every expensive layer:
#
#   docker build --target api   -t equitable-api:dev   .
#   docker build --target agent -t equitable-agent:dev .
#
# Both need Chromium. That is not an oversight: `main.py` imports
# `services.scraper` at module scope, and the /pantries/discover and
# /pantries/{id}/ingest endpoints scrape live via Crawl4AI, so the API needs a
# browser just as the refresh agent does. Sharing one `runtime` stage means the
# ~700 MB Chromium + apt layer is built and cached exactly once instead of
# twice.
#
# `agent` is deliberately the LAST stage, so a bare `docker build .` still
# produces the refresh-agent image that ECS (ADR-019) expects. That path keeps
# working unchanged during the Kubernetes migration.
#
# Audit notes vs. the previous single-stage version (ADR-022):
#   - base image is now digest-pinned, not floating on a tag
#   - build toolchain no longer ships in the runtime image
#   - runs as a non-root user (uid 10001) instead of root
#   - unchanged on purpose: the agent CMD, PLAYWRIGHT_BROWSERS_PATH, and the
#     Python version, so the ECS task definition needs no edits

# ─────────────────────────────────────────────────────────────────────────────
# Base — pinned by multi-arch index digest so amd64 (ECS/CI) and arm64 (local
# Apple Silicon / kind) both resolve, while the bytes stay reproducible. A bare
# `python:3.12-slim-bookworm` tag silently changes under you between builds.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# ─────────────────────────────────────────────────────────────────────────────
# Builder — compiles wheels into a venv. gcc and the -dev headers live only
# here; they are never copied into the runtime image.
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV"

# Dependency layer first: application edits do not invalidate the pip install.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Runtime — everything both images share: the venv, Chromium, the app code,
# and the unprivileged user.
# ─────────────────────────────────────────────────────────────────────────────
FROM base AS runtime

# ca-certificates is required for TLS to Atlas, Gemini, Jina and LangSmith.
# tini reaps zombies and forwards signals, which matters for the CronJob: an
# unreaped PID 1 ignores SIGTERM, so activeDeadlineSeconds / pod eviction would
# escalate to SIGKILL and the run would lose its chance to exit cleanly.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Chromium + its shared-library dependencies. Must run in the runtime lineage,
# not the builder: `--with-deps` installs apt packages (libnss3, libatk, ...)
# that Chromium dlopens at run time, and copying only /ms-playwright across
# stages would leave those behind and fail at the first scrape.
RUN python -m playwright install --with-deps chromium \
    && chmod -R a+rX /ms-playwright \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged user. A high, explicit uid keeps the image compatible with a
# cluster that enforces runAsNonRoot, which cannot verify a username alone.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app

# Crawl4AI creates a SQLite cache under $HOME at IMPORT time (async_database.py
# runs os.makedirs at module scope), so `import main` fails outright if $HOME is
# not writable. useradd leaves HOME=/home/app pointing at a directory that does
# not exist, and the runtime filesystem is read-only anyway, so point it at /tmp
# — which is a writable emptyDir in both the Deployment and the CronJob.
# Creating a real /home/app would not help: it would sit on the read-only root.
ENV HOME=/tmp

# Application code last — the layer that actually changes between builds.
# tests/, venv/ and .env are excluded via .dockerignore.
COPY . .

RUN chown -R 10001:10001 /app

USER 10001:10001

ENTRYPOINT ["/usr/bin/tini", "--"]

# ─────────────────────────────────────────────────────────────────────────────
# API — the FastAPI service behind the Kubernetes Deployment / Service / Ingress
# ─────────────────────────────────────────────────────────────────────────────
FROM runtime AS api

ENV PORT=8000
EXPOSE 8000

# One worker per container: scale with replicas + the HPA, not with in-pod
# processes. Multiple uvicorn workers inside a pod hide load from the HPA's
# per-pod CPU metric and multiply the Mongo connection pool per pod.
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]

# ─────────────────────────────────────────────────────────────────────────────
# Agent — the scheduled refresh job (Kubernetes CronJob; also the ECS image)
# Last stage on purpose: `docker build .` with no --target yields this.
# ─────────────────────────────────────────────────────────────────────────────
FROM runtime AS agent

CMD ["python", "-m", "agent.refresh"]
