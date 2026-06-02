"""
health.py - Health check endpoint for the Store Intelligence System.

GET /health returns:
- service status
- last event timestamp
- total event count
- stale feed warning (if no events in last 5 minutes)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter

from app.models import HealthResponse, get_db_connection

logger = logging.getLogger("store_intelligence")

router = APIRouter()

# If no event received in the last N minutes, flag as stale
STALE_THRESHOLD_MINUTES = 5


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Return the health status of the Store Intelligence System.

    Checks:
    - Database connectivity
    - Last event timestamp
    - Stale feed detection
    """
    try:
        conn = get_db_connection()
        try:
            # Total events
            row = conn.execute("SELECT COUNT(*) as cnt FROM events").fetchone()
            total_events = row["cnt"] if row else 0

            # Last event timestamp
            row = conn.execute(
                "SELECT MAX(timestamp) as last_ts FROM events"
            ).fetchone()
            last_event_ts = row["last_ts"] if row else None

            # Stale feed check
            stale_warning = False
            message = "Service is operational."

            if last_event_ts:
                try:
                    last_dt = datetime.fromisoformat(last_event_ts)
                    threshold = datetime.utcnow() - timedelta(
                        minutes=STALE_THRESHOLD_MINUTES
                    )
                    if last_dt < threshold:
                        stale_warning = True
                        message = (
                            f"WARNING: No events received in the last "
                            f"{STALE_THRESHOLD_MINUTES} minutes. "
                            f"Last event at {last_event_ts}."
                        )
                except (ValueError, TypeError):
                    message = "Service operational. Unable to parse last event timestamp."
            elif total_events == 0:
                message = "Service operational. No events ingested yet."

            return HealthResponse(
                status="healthy",
                last_event_timestamp=last_event_ts,
                total_events=total_events,
                stale_feed_warning=stale_warning,
                message=message,
            )
        finally:
            conn.close()

    except Exception as e:
        logger.error("health_check_failed", extra={"error": str(e)})
        return HealthResponse(
            status="unhealthy",
            message=f"Database connection error: {str(e)}",
            stale_feed_warning=True,
        )
