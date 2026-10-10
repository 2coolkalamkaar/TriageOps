"""
FastAPI REST API for TriageOps.

Endpoints:
  POST /triage         — Run the full triage pipeline   (auth + rate limited)
  GET  /health         — Health check                   (public)
  GET  /runbooks       — List available runbooks        (auth)

Run with:
  uvicorn triageops.api:app --host 0.0.0.0 --port 8000

Security configuration (environment variables):
  TRIAGEOPS_API_KEYS            Comma-separated API keys. When set, protected endpoints
                                require `Authorization: Bearer <key>` or `X-API-Key: <key>`.
                                When unset, the API is open (a warning is logged at startup).
  TRIAGEOPS_CORS_ORIGINS        Comma-separated allowed browser origins. Default: none
                                (the bundled web UI is same-origin and needs no CORS).
  TRIAGEOPS_RATE_LIMIT_PER_MIN  Max /triage requests per client per minute. Default 20, 0 disables.
                                In-memory and per-process: with N workers the effective limit is N×.
                                Behind a reverse proxy, run uvicorn with --proxy-headers and
                                --forwarded-allow-ips so the client IP is the real one.
"""

import hmac
import logging
import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .llm import LLMUnavailableError, get_provider
from .pipeline import _runbooks, run_triage
from .render import to_markdown

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def _csv_env(name: str) -> list[str]:
    return [v.strip() for v in os.environ.get(name, "").split(",") if v.strip()]


API_KEYS: list[str] = _csv_env("TRIAGEOPS_API_KEYS")
CORS_ORIGINS: list[str] = _csv_env("TRIAGEOPS_CORS_ORIGINS")
RATE_LIMIT_PER_MIN: int = int(os.environ.get("TRIAGEOPS_RATE_LIMIT_PER_MIN", "20"))

if not API_KEYS:
    logger.warning(
        "TRIAGEOPS_API_KEYS is not set — /triage is unauthenticated. "
        "Anyone who can reach this server can spend your LLM quota."
    )
if get_provider() == "offline":
    logger.warning(
        "No LLM provider configured (GEMINI_API_KEY / GOOGLE_CLOUD_PROJECT) — "
        "running in DEGRADED offline-heuristic mode."
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TriageOps",
    description=(
        "DevOps incident triage agent — classifies, diagnoses, and reports "
        "infrastructure failures from raw logs and error messages."
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
)

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Request-ID"],
    )

# Mount static web directory
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class TriageRequest(BaseModel):
    text: str = Field(
        description="Raw log, error message, command output, or problem description to triage.",
        min_length=1,
        max_length=50_000,
    )
    format: str = Field(
        default="json",
        description="Response format: 'json' (default) or 'markdown'.",
        pattern="^(json|markdown)$",
    )

    model_config = {"json_schema_extra": {
        "example": {
            "text": "kubectl describe pod web-7d9\nStatus: CrashLoopBackOff\nExit Code: 1",
            "format": "json",
        }
    }}


class TriageResponse(BaseModel):
    success: bool
    format: str
    data: Any  # Report dict (json) or markdown string
    markdown: str | None = None
    latency_ms: int | None = None
    engine: str | None = None
    degraded: bool = False


class HealthResponse(BaseModel):
    status: str
    version: str
    runbooks_loaded: int
    llm_provider: str
    auth_enabled: bool


class RunbooksResponse(BaseModel):
    runbooks: list[str]
    count: int


# ---------------------------------------------------------------------------
# Auth & rate limiting
# ---------------------------------------------------------------------------

def _extract_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


def require_api_key(request: Request) -> None:
    if not API_KEYS:
        return
    supplied = _extract_key(request) or ""
    if not any(hmac.compare_digest(supplied.encode(), k.encode()) for k in API_KEYS):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )


class _RateLimiter:
    """Sliding-window limiter keyed by API key (if any) or client IP."""

    def __init__(self, limit: int, window_s: float = 60.0, max_clients: int = 10_000) -> None:
        self.limit = limit
        self.window_s = window_s
        self.max_clients = max_clients
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, client: str) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until a slot frees up."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(client)
            if hits is None:
                if len(self._hits) >= self.max_clients:
                    self._evict(now)
                hits = self._hits[client] = deque()
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return self.window_s - (now - hits[0])
            hits.append(now)
            return None

    def _evict(self, now: float) -> None:
        stale = [c for c, h in self._hits.items() if not h or now - h[-1] >= self.window_s]
        for c in stale:
            del self._hits[c]
        if len(self._hits) >= self.max_clients:
            self._hits.clear()


_limiter = _RateLimiter(RATE_LIMIT_PER_MIN) if RATE_LIMIT_PER_MIN > 0 else None


def rate_limit(request: Request) -> None:
    if _limiter is None:
        return
    key = _extract_key(request)
    client = f"key:{key}" if key else f"ip:{request.client.host if request.client else 'unknown'}"
    retry_after = _limiter.check(client)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )


# ---------------------------------------------------------------------------
# Middleware: request ID + logging
# ---------------------------------------------------------------------------

@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = request_id
    start = time.monotonic()
    response = await call_next(request)
    latency = int((time.monotonic() - start) * 1000)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "%s %s → %d (%dms) request_id=%s",
        request.method,
        request.url.path,
        response.status_code,
        latency,
        request_id,
    )
    return response


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

DOCS_FILE = Path(__file__).parent.parent.parent / "docs" / "TriageOps_Documentation.html"

@app.get("/", include_in_schema=False)
async def index():
    """Serve the TriageOps Command Center frontend."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"message": "TriageOps API is running. Visit /docs for OpenAPI specs."})


@app.get("/documentation", include_in_schema=False)
async def documentation():
    """Serve the complete visual documentation HTML page."""
    if DOCS_FILE.exists():
        return FileResponse(str(DOCS_FILE))
    return JSONResponse({"error": "Documentation file not found"}, status_code=404)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    """Health check — confirms the API is running and shows runbook count."""
    return HealthResponse(
        status="ok",
        version=__version__,
        runbooks_loaded=len(_runbooks),
        llm_provider=get_provider(),
        auth_enabled=bool(API_KEYS),
    )


@app.get("/runbooks", response_model=RunbooksResponse, tags=["System"], dependencies=[Depends(require_api_key)])
async def list_runbooks() -> RunbooksResponse:
    """List all runbooks available for retrieval."""
    names = _runbooks.list_runbooks()
    return RunbooksResponse(runbooks=names, count=len(names))


@app.get("/runbooks/{name}", tags=["System"], dependencies=[Depends(require_api_key)])
async def get_runbook(name: str):
    """Retrieve raw markdown content of a specific runbook."""
    content = _runbooks.get_runbook(name)
    if not content:
        raise HTTPException(status_code=404, detail=f"Runbook '{name}' not found")
    return {"name": name, "content": content}


# Plain `def` (not async): run_triage makes blocking LLM calls, so FastAPI runs
# this in its threadpool instead of stalling the event loop for every client.
@app.post(
    "/triage",
    response_model=TriageResponse,
    tags=["Triage"],
    dependencies=[Depends(require_api_key), Depends(rate_limit)],
)
def triage(body: TriageRequest, request: Request) -> TriageResponse:
    """
    Run the TriageOps pipeline on the provided text.

    Returns a structured incident report in JSON or markdown format.
    """
    request_id = _request_id(request)
    try:
        report = run_triage(body.text)
    except LLMUnavailableError:
        logger.exception("LLM unavailable request_id=%s", request_id)
        raise HTTPException(
            status_code=503,
            detail=f"LLM provider unavailable — please retry shortly (request_id={request_id})",
            headers={"Retry-After": "30"},
        )
    except Exception:
        logger.exception("Pipeline error request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error while triaging (request_id={request_id})",
        )

    md = to_markdown(report)
    return TriageResponse(
        success=True,
        format=body.format,
        data=md if body.format == "markdown" else report.model_dump(),
        markdown=md,
        latency_ms=report.latency_ms,
        engine=report.engine,
        degraded=report.degraded,
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request", "detail": jsonable_encoder(exc.errors())},
    )
