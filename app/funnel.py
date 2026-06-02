"""
funnel.py - Visitor funnel endpoint for the Store Intelligence System.

GET /stores/{store_id}/funnel calculates the conversion funnel:
    Entry → Zone Visit → Billing Queue → Purchase

Rules:
- Each visitor is counted only ONCE per funnel stage (no double-counting).
- RE-ENTRY visitors count towards entries but are not double-counted.
- A "Purchase" is a visitor who joined billing and did NOT abandon.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.models import FunnelResponse, FunnelStage, fetch_non_staff_events

logger = logging.getLogger("store_intelligence")

router = APIRouter()


@router.get("/stores/{store_id}/funnel", response_model=FunnelResponse)
async def get_store_funnel(store_id: str):
    """
    Compute the visitor funnel for a store.

    Stages:
    1. Entry     – unique visitors who entered (ENTRY or REENTRY)
    2. Zone Visit – subset of entrants who visited at least one zone
    3. Billing Queue – subset who joined the billing queue
    4. Purchase  – subset who completed purchase (joined queue, did not abandon)
    """
    events = fetch_non_staff_events(store_id)

    # Sets to track unique visitors per stage
    entered: set[str] = set()
    zone_visited: set[str] = set()
    billing_joined: set[str] = set()
    billing_abandoned: set[str] = set()

    for e in events:
        vid = e["visitor_id"]
        etype = e["event_type"]

        if etype in ("ENTRY", "REENTRY"):
            entered.add(vid)
        elif etype in ("ZONE_ENTER", "ZONE_DWELL", "ZONE_EXIT"):
            zone_visited.add(vid)
        elif etype == "BILLING_QUEUE_JOIN":
            billing_joined.add(vid)
        elif etype == "BILLING_QUEUE_ABANDON":
            billing_abandoned.add(vid)

    # Zone visitors must be a subset of entrants
    zone_visited = zone_visited & entered
    # Billing joiners must have entered the store
    billing_joined_valid = billing_joined & entered
    # Purchasers = joined billing minus abandoned
    purchasers = billing_joined_valid - billing_abandoned

    stages = [
        FunnelStage(stage="Entry", count=len(entered)),
        FunnelStage(stage="Zone Visit", count=len(zone_visited)),
        FunnelStage(stage="Billing Queue", count=len(billing_joined_valid)),
        FunnelStage(stage="Purchase", count=len(purchasers)),
    ]

    return FunnelResponse(stages=stages)
