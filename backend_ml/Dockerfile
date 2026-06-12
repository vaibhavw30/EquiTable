# backend_ml/Dockerfile
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# System deps needed for the Playwright/Chromium install step
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium + its OS dependencies for Crawl4AI
RUN python -m playwright install --with-deps chromium

# Copy application code (tests/venv excluded via .dockerignore)
COPY . .

# Run the refresh job
CMD ["python", "-m", "agent.refresh"]
