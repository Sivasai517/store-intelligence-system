"""
metrics.py - Store metrics endpoint for the Store Intelligence System.

GET /stores/{store_id}/metrics returns:
- unique_visitors (non-staff)
- conversion_rate  (purchasers / unique visitors)
- avg_dwell_time   (per zone, in ms)
- queue_depth      (current count in billing queue)
- abandonment_rate (queue abandons / queue joins)

All metrics exclude staff members (is_staff = true).
"""

from __future__ import annotations

import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException

from app.models import MetricsResponse, fetch_non_staff_events

logger = logging.getLogger("store_intelligence")

router = APIRouter()


@router.get("/stores/{store_id}/metrics", response_model=MetricsResponse)
async def get_store_metrics(store_id: str):
    """
    Compute real-time metrics for a given store.

    Excludes staff from all calculations.
    """
    events = fetch_non_staff_events(store_id)

    if not events:
        return MetricsResponse()

    # ---- Unique visitors ----
    # A visitor is anyone who triggered an ENTRY or REENTRY event
    visitor_ids = {e["visitor_id"] for e in events if e["event_type"] in ("ENTRY", "REENTRY")}
    unique_visitors = len(visitor_ids)

    # ---- Conversion rate ----
    # purchasers = (People who joined billing queue) - (People who abandoned the queue)
    billing_joiners = {e["visitor_id"] for e in events if e["event_type"] == "BILLING_QUEUE_JOIN"}
    billing_abandoners = {e["visitor_id"] for e in events if e["event_type"] == "BILLING_QUEUE_ABANDON"}
    
    purchasers = billing_joiners - billing_abandoners
    conversion_rate = (
        round(len(purchasers) / unique_visitors, 4) if unique_visitors > 0 else 0.0
    )

    # ---- Average dwell time per zone ----
    zone_dwells: dict[str, list[int]] = defaultdict(list)
    for e in events:
        if e["event_type"] == "ZONE_DWELL" and e["zone_id"]:
            zone_dwells[e["zone_id"]].append(e["dwell_ms"])

    avg_dwell_time = {}
    for zone_id, dwells in zone_dwells.items():
        avg_dwell_time[zone_id] = round(sum(dwells) / len(dwells), 2)

    # ---- Queue depth (current) ----
    # People who joined but haven't exited or abandoned
    queue_in = set()
    for e in events:
        vid = e["visitor_id"]
        if e["event_type"] == "BILLING_QUEUE_JOIN":
            queue_in.add(vid)
        elif e["event_type"] in ("BILLING_QUEUE_ABANDON", "EXIT"):
            queue_in.discard(vid)
    queue_depth = len(queue_in)

    # ---- Abandonment rate ----
    total_joins = len(billing_joiners)
    total_abandons = len(billing_abandoners)
    abandonment_rate = (
        round(total_abandons / total_joins, 4) if total_joins > 0 else 0.0
    )

    return MetricsResponse(
        unique_visitors=unique_visitors,
        conversion_rate=conversion_rate,
        avg_dwell_time=avg_dwell_time,
        queue_depth=queue_depth,
        abandonment_rate=abandonment_rate,
    )
