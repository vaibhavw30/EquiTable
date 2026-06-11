# Error Monitoring & Logging Strategy

Lightweight error handling for a passion project — enough to catch problems without enterprise overhead.

## Backend (FastAPI on Render)

### Structured Logging

Use Python's built-in `logging` with JSON formatting so Render's log viewer can parse it.

```python
# backend_ml/logging_config.py
import logging
import json
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger = logging.getLogger("equitable")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return logger
```

### What to Log

| Event                     | Level    | Example                                                                              |
| ------------------------- | -------- | ------------------------------------------------------------------------------------ |
| Request received          | INFO     | `{"method": "GET", "path": "/pantries", "status": 200, "duration_ms": 45}`           |
| Scrape started            | INFO     | `{"event": "scrape_start", "url": "...", "city": "Atlanta"}`                         |
| Scrape completed          | INFO     | `{"event": "scrape_complete", "url": "...", "confidence": 8, "duration_ms": 3200}`   |
| Scrape failed             | ERROR    | `{"event": "scrape_failed", "url": "...", "error": "Timeout after 10s"}`             |
| Extraction low confidence | WARNING  | `{"event": "low_confidence", "pantry": "...", "confidence": 3, "url": "..."}`        |
| Validation rejection      | WARNING  | `{"event": "validation_failed", "reason": "confidence out of range", "data": {...}}` |
| DB connection error       | ERROR    | `{"event": "db_error", "error": "..."}`                                              |
| Unhandled exception       | CRITICAL | Full stack trace                                                                     |

### FastAPI Middleware for Request Logging

```python
# backend_ml/middleware/logging.py
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("equitable")

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 2)

        logger.info(
            f"{request.method} {request.url.path}",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration,
            }
        )
        return response
```

### Global Exception Handler

```python
# In main.py
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.critical(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "INTERNAL_ERROR"}
    )
```

### Scraping Pipeline Logging

Every scrape produces a log entry regardless of success/failure:

```python
# In ingestion_pipeline.py
async def ingest_pantry(url: str, city: str) -> dict:
    logger.info(f"Scrape starting", extra={"url": url, "city": city})

    try:
        markdown = await scrape(url)
        data = await extract(markdown)
        validated = validate(data)

        logger.info(f"Scrape complete", extra={
            "url": url,
            "confidence": validated.get("confidence"),
            "status": validated.get("status"),
        })
        return validated

    except ScrapeError as e:
        logger.error(f"Scrape failed", extra={"url": url, "error": str(e)})
        raise
    except ExtractionError as e:
        logger.error(f"Extraction failed", extra={"url": url, "error": str(e)})
        raise
    except ValidationError as e:
        logger.warning(f"Validation failed", extra={"url": url, "reason": str(e)})
        raise
```

## Frontend (React on Vercel)

### React Error Boundary

Wrap the entire app so a single component crash doesn't white-screen everything:

```jsx
// frontend/src/components/ErrorBoundary.jsx
import { Component } from "react";

export class ErrorBoundary extends Component {
  state = { hasError: false, error: null };

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("React Error Boundary caught:", error, errorInfo);
    // Future: send to error tracking service
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen p-8">
          <h1 className="text-2xl font-bold mb-4">Something went wrong</h1>
          <p className="text-gray-600 mb-4">
            The app encountered an unexpected error. Please try refreshing.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
          >
            Refresh Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

**Usage in App.jsx:**

```jsx
<ErrorBoundary>
  <BrowserRouter>
    <Routes>...</Routes>
  </BrowserRouter>
</ErrorBoundary>
```

### Page-Level Error Boundaries

Wrap each major page so a map crash doesn't take down the landing page:

```jsx
<Route
  path="/map"
  element={
    <ErrorBoundary>
      <MapPage />
    </ErrorBoundary>
  }
/>
```

### API Error Handling Pattern

Every API call in hooks should surface errors to the UI:

```jsx
// In any data-fetching hook
const [error, setError] = useState(null);

// In the component using the hook
if (error) {
  return <ErrorToast message={error} onDismiss={() => setError(null)} />;
}
```

### Console Error Tracking

For now, `console.error` is sufficient. When the project grows, consider adding a lightweight service:

| Tool                      | Cost                  | Effort       |
| ------------------------- | --------------------- | ------------ |
| Console logging (current) | Free                  | None         |
| Sentry free tier          | Free (5K events/mo)   | 30 min setup |
| LogRocket free tier       | Free (1K sessions/mo) | 30 min setup |

**Recommendation**: Stay with console logging until the app has real users. Add Sentry free tier when you deploy multi-city (Phase 1) since that's when silent failures become harder to catch manually.

## Health Monitoring

### Backend Health Check

The existing `GET /` endpoint serves as a basic health check. Enhance it slightly:

```python
@app.get("/")
async def health_check():
    try:
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
```

### Uptime Monitoring (Optional)

Use a free uptime monitor to alert if Render's free tier goes down and doesn't wake up:

- **UptimeRobot** (free, 5-min intervals) — ping `GET /` on the Render URL
- This also keeps the Render free tier warm, reducing cold starts

## Testing the Error Handling

```python
# backend_ml/tests/test_error_handling.py

class TestErrorHandling:
    async def test_unhandled_exception_returns_500(self, client):
        """Global handler catches unhandled exceptions."""
        # Trigger an endpoint that raises unexpectedly
        ...
        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"

    async def test_404_returns_structured_error(self, client):
        response = await client.get("/nonexistent")
        assert response.status_code == 404

    async def test_validation_error_returns_422(self, client):
        response = await client.get("/pantries/nearby", params={"lat": "abc"})
        assert response.status_code == 422

    async def test_health_check_reports_db_status(self, client):
        response = await client.get("/")
        data = response.json()
        assert "database" in data
        assert "status" in data
```

```jsx
// frontend/src/__tests__/ErrorBoundary.test.jsx

describe("ErrorBoundary", () => {
  it("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <div>Content</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Content")).toBeInTheDocument();
  });

  it("renders fallback UI on child error", () => {
    const ThrowError = () => {
      throw new Error("Test");
    };
    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
  });

  it("provides refresh button", () => {
    const ThrowError = () => {
      throw new Error("Test");
    };
    render(
      <ErrorBoundary>
        <ThrowError />
      </ErrorBoundary>,
    );
    expect(
      screen.getByRole("button", { name: /refresh/i }),
    ).toBeInTheDocument();
  });
});
```
