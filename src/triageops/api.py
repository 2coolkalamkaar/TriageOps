"""
FastAPI REST API for TriageOps.

Endpoints:
  POST /triage         — Run the full triage pipeline
  GET  /health         — Health check
  GET  /runbooks       — List available runbooks

Run with:
  uvicorn triageops.api:app --host 0.0.0.0 --port 8000 --reload
"""

import logging
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .pipeline import _runbooks, run_triage
from .render import to_markdown

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"

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

# CORS — allow local frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    latency_ms: int | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    runbooks_loaded: int


class RunbooksResponse(BaseModel):
    runbooks: list[str]
    count: int


# ---------------------------------------------------------------------------
# Middleware: request logging
# ---------------------------------------------------------------------------

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    latency = int((time.monotonic() - start) * 1000)
    logger.info(
        "%s %s → %d (%dms)",
        request.method,
        request.url.path,
        response.status_code,
        latency,
    )
    return response


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def index():
    """Serve the TriageOps Command Center frontend."""
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"message": "TriageOps API is running. Visit /docs for OpenAPI specs."})


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health() -> HealthResponse:
    """Health check — confirms the API is running and shows runbook count."""
    return HealthResponse(
        status="ok",
        version=__version__,
        runbooks_loaded=len(_runbooks),
    )


@app.get("/runbooks", response_model=RunbooksResponse, tags=["System"])
async def list_runbooks() -> RunbooksResponse:
    """List all runbooks available for retrieval."""
    names = _runbooks.list_runbooks()
    return RunbooksResponse(runbooks=names, count=len(names))


@app.get("/runbooks/{name}", tags=["System"])
async def get_runbook(name: str):
    """Retrieve raw markdown content of a specific runbook."""
    content = _runbooks.get_runbook(name)
    if not content:
        raise HTTPException(status_code=404, detail=f"Runbook '{name}' not found")
    return {"name": name, "content": content}


@app.post("/triage", response_model=TriageResponse, tags=["Triage"])
async def triage(body: TriageRequest) -> TriageResponse:
    """
    Run the TriageOps pipeline on the provided text.

    Returns a structured incident report in JSON or markdown format.
    """
    try:
        report = run_triage(body.text)
    except Exception as exc:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(exc))

    if body.format == "markdown":
        return TriageResponse(
            success=True,
            format="markdown",
            data=to_markdown(report),
            latency_ms=report.latency_ms,
        )

    return TriageResponse(
        success=True,
        format="json",
        data=report.model_dump(),
        latency_ms=report.latency_ms,
    )


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(422)
async def validation_error_handler(request: Request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": "Invalid request", "detail": exc.errors()},
    )
