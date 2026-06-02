"""
models.py - Pydantic schemas and SQLite database management for the Store Intelligence System.

Defines the Event schema, database initialization, and helper functions for
persisting and retrieving events from SQLite.
"""

from __future__ import annotations

import os
import sqlite3
import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

def get_db_path() -> str:
    """Return the current database path from environment or default."""
    return os.getenv("DATABASE_PATH", "store_intelligence.db")


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """All recognised visitor event types."""
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    ZONE_ENTER = "ZONE_ENTER"
    ZONE_EXIT = "ZONE_EXIT"
    ZONE_DWELL = "ZONE_DWELL"
    BILLING_QUEUE_JOIN = "BILLING_QUEUE_JOIN"
    BILLING_QUEUE_ABANDON = "BILLING_QUEUE_ABANDON"
    REENTRY = "REENTRY"


class Severity(str, Enum):
    """Anomaly severity levels."""
    INFO = "INFO"
    WARN = "WARN"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------

class EventPayload(BaseModel):
    """Schema for a single visitor event produced by the detection pipeline."""
    event_id: str = Field(..., description="UUID for this event")
    store_id: str = Field(..., description="Store identifier")
    camera_id: str = Field(..., description="Camera that captured the event")
    visitor_id: str = Field(..., description="Tracked person identifier")
    event_type: EventType = Field(..., description="Type of event")
    timestamp: str = Field(..., description="ISO-8601 timestamp")
    zone_id: str = Field(default="", description="Zone where event occurred")
    dwell_ms: int = Field(default=0, description="Dwell time in milliseconds")
    is_staff: bool = Field(default=False, description="True if person is staff")
    confidence: float = Field(default=0.0, description="Detection confidence 0-1")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Extra metadata")


class MetricsResponse(BaseModel):
    """Response schema for the /stores/{id}/metrics endpoint."""
    unique_visitors: int = 0
    conversion_rate: float = 0.0
    avg_dwell_time: dict[str, float] = Field(default_factory=dict)
    queue_depth: int = 0
    abandonment_rate: float = 0.0


class FunnelStage(BaseModel):
    """A single funnel stage with count."""
    stage: str
    count: int


class FunnelResponse(BaseModel):
    """Response for the funnel endpoint."""
    stages: list[FunnelStage]


class HeatmapZone(BaseModel):
    """Zone-level heatmap data."""
    zone_id: str
    frequency: int = 0
    avg_dwell_ms: float = 0.0
    normalized_score: float = 0.0


class HeatmapResponse(BaseModel):
    """Response for the heatmap endpoint."""
    zones: list[HeatmapZone]


class AnomalyItem(BaseModel):
    """A single detected anomaly."""
    anomaly_type: str
    severity: Severity
    description: str
    suggested_action: str
    detected_at: str = ""


class AnomalyResponse(BaseModel):
    """Response for the anomalies endpoint."""
    anomalies: list[AnomalyItem]


class HealthResponse(BaseModel):
    """Response for the health check endpoint."""
    status: str = "healthy"
    last_event_timestamp: Optional[str] = None
    total_events: int = 0
    stale_feed_warning: bool = False
    message: str = ""


# ---------------------------------------------------------------------------
# Database Helpers
# ---------------------------------------------------------------------------

def get_db_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row factory enabled."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    """Create the events table if it does not exist."""
    conn = get_db_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id    TEXT PRIMARY KEY,
                store_id    TEXT NOT NULL,
                camera_id   TEXT NOT NULL,
                visitor_id  TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                timestamp   TEXT NOT NULL,
                zone_id     TEXT DEFAULT '',
                dwell_ms    INTEGER DEFAULT 0,
                is_staff    INTEGER DEFAULT 0,
                confidence  REAL DEFAULT 0.0,
                metadata    TEXT DEFAULT '{}'
            );
        """)
        # Indexes for fast queries
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_store
            ON events (store_id);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_store_type
            ON events (store_id, event_type);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_events_visitor
            ON events (store_id, visitor_id);
        """)
        conn.commit()
    finally:
        conn.close()


def insert_event(event: EventPayload) -> bool:
    """
    Insert an event into SQLite. Returns True if inserted, False if duplicate.
    Uses INSERT OR IGNORE for idempotent ingestion (deduplication on event_id).
    """
    conn = get_db_connection()
    try:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO events
                (event_id, store_id, camera_id, visitor_id, event_type,
                 timestamp, zone_id, dwell_ms, is_staff, confidence, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.store_id,
                event.camera_id,
                event.visitor_id,
                event.event_type.value,
                event.timestamp,
                event.zone_id,
                event.dwell_ms,
                int(event.is_staff),
                event.confidence,
                json.dumps(event.metadata),
            ),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def fetch_events(store_id: str, event_type: Optional[str] = None) -> list[dict]:
    """
    Retrieve events for a store, optionally filtered by event_type.
    Returns list of dicts.
    """
    conn = get_db_connection()
    try:
        if event_type:
            rows = conn.execute(
                "SELECT * FROM events WHERE store_id = ? AND event_type = ? ORDER BY timestamp",
                (store_id, event_type),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM events WHERE store_id = ? ORDER BY timestamp",
                (store_id,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_non_staff_events(store_id: str) -> list[dict]:
    """Retrieve all non-staff events for a store."""
    conn = get_db_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM events WHERE store_id = ? AND is_staff = 0 ORDER BY timestamp",
            (store_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
