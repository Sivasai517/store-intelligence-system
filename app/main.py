"""
main.py - FastAPI application entry point for the Store Intelligence System.

Sets up:
- Structured JSON logging with trace_id per request
- CORS middleware
- Database initialisation on startup
- All API routers
"""

from __future__ import annotations

import time
import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pythonjsonlogger import jsonlogger

from app.models import init_db
from app.ingestion import router as ingestion_router
from app.metrics import router as metrics_router
from app.funnel import router as funnel_router
from app.anomalies import router as anomalies_router
from app.health import router as health_router


# ---------------------------------------------------------------------------
# Structured JSON Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("store_intelligence")
logger.setLevel(logging.INFO)

handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
handler.setFormatter(formatter)
logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise database on startup."""
    logger.info("Initialising SQLite database...")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down Store Intelligence System.")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Store Intelligence System",
    description=(
        "Retail analytics API powered by CCTV-based person detection and tracking. "
        "Processes visitor events and generates real-time metrics, funnel analysis, "
        "heatmaps, and anomaly detection."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS – allow dashboard and dev tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request Logging Middleware
# ---------------------------------------------------------------------------

@app.middleware("http")
async def logging_middleware(request: Request, call_next) -> Response:
    """
    Log every request with:
    - trace_id (unique per request)
    - endpoint
    - store_id (extracted from path if present)
    - latency_ms
    - status_code
    """
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id

    # Extract store_id from path parameters if available
    store_id = "N/A"
    path_parts = request.url.path.strip("/").split("/")
    if len(path_parts) >= 2 and path_parts[0] == "stores":
        store_id = path_parts[1]

    start_time = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

    logger.info(
        "request_processed",
        extra={
            "trace_id": trace_id,
            "endpoint": request.url.path,
            "method": request.method,
            "store_id": store_id,
            "latency_ms": latency_ms,
            "status_code": response.status_code,
        },
    )

    # Attach trace_id to response headers for debugging
    response.headers["X-Trace-ID"] = trace_id
    return response


# ---------------------------------------------------------------------------
# Register Routers
# ---------------------------------------------------------------------------

app.include_router(ingestion_router, tags=["Ingestion"])
app.include_router(metrics_router, tags=["Metrics"])
app.include_router(funnel_router, tags=["Funnel"])
app.include_router(anomalies_router, tags=["Anomalies & Heatmap"])
app.include_router(health_router, tags=["Health"])


# ---------------------------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------------------------

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint returning API information."""
    return {
        "service": "Store Intelligence System",
        "version": "1.0.0",
        "docs": "/docs",
    }
