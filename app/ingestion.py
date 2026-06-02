"""
ingestion.py - Event ingestion endpoint for the Store Intelligence System.

Handles POST /events/ingest with:
- Single and batch event ingestion
- Idempotent writes (duplicate event_id silently ignored)
- Input validation via Pydantic
"""

from __future__ import annotations

import logging
from typing import Union

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models import EventPayload, insert_event

logger = logging.getLogger("store_intelligence")

router = APIRouter()


class IngestRequest(BaseModel):
    """Accepts a single event or a list of events."""
    events: Union[list[EventPayload], EventPayload]


class IngestResponse(BaseModel):
    """Response after ingesting events."""
    accepted: int
    duplicates: int
    total: int


@router.post("/events/ingest", response_model=IngestResponse)
async def ingest_events(payload: IngestRequest):
    """
    Ingest one or more visitor events into the system.

    - Deduplication is performed on event_id (INSERT OR IGNORE).
    - POST requests are idempotent: resubmitting the same event is safe.

    Returns count of accepted (new) and duplicate events.
    """
    # Normalise to list
    events = payload.events if isinstance(payload.events, list) else [payload.events]

    if not events:
        raise HTTPException(status_code=400, detail="No events provided")

    accepted = 0
    duplicates = 0

    for event in events:
        try:
            inserted = insert_event(event)
            if inserted:
                accepted += 1
                logger.info(
                    "event_ingested",
                    extra={
                        "event_id": event.event_id,
                        "store_id": event.store_id,
                        "event_type": event.event_type.value,
                        "visitor_id": event.visitor_id,
                    },
                )
            else:
                duplicates += 1
                logger.debug(
                    "duplicate_event_skipped",
                    extra={"event_id": event.event_id},
                )
        except Exception as e:
            logger.error(
                "event_ingestion_failed",
                extra={"event_id": event.event_id, "error": str(e)},
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to ingest event {event.event_id}: {str(e)}",
            )

    return IngestResponse(
        accepted=accepted,
        duplicates=duplicates,
        total=len(events),
    )
