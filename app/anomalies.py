"""
anomalies.py - Anomaly detection and heatmap endpoints for the Store Intelligence System.

GET /stores/{store_id}/heatmap
    Returns zone frequency, average dwell, and normalised score (0-100).

GET /stores/{store_id}/anomalies
    Detects three anomaly types:
    1. Queue Spike   – billing queue depth exceeds threshold
    2. Conversion Drop – conversion rate falls below threshold
    3. Dead Zone     – zones with zero or near-zero traffic
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter

from app.models import (
    AnomalyItem,
    AnomalyResponse,
    HeatmapResponse,
    HeatmapZone,
    Severity,
    fetch_non_staff_events,
)

logger = logging.getLogger("store_intelligence")

router = APIRouter()

# ---------------------------------------------------------------------------
# Configuration thresholds
# ---------------------------------------------------------------------------
QUEUE_SPIKE_THRESHOLD = 5         # More than N people in queue → spike
CONVERSION_DROP_THRESHOLD = 0.05  # Below 5% → conversion drop
DEAD_ZONE_THRESHOLD = 2           # Fewer than N visits → dead zone


# ---------------------------------------------------------------------------
# Heatmap Endpoint
# ---------------------------------------------------------------------------

@router.get("/stores/{store_id}/heatmap", response_model=HeatmapResponse)
async def get_store_heatmap(store_id: str):
    """
    Return zone-level heatmap data:
    - frequency: total number of zone visits (ZONE_ENTER events)
    - avg_dwell_ms: average dwell time in milliseconds
    - normalized_score: 0-100 score based on relative frequency
    """
    events = fetch_non_staff_events(store_id)

    zone_frequency: dict[str, int] = defaultdict(int)
    zone_dwells: dict[str, list[int]] = defaultdict(list)

    for e in events:
        if e["event_type"] == "ZONE_ENTER" and e["zone_id"]:
            zone_frequency[e["zone_id"]] += 1
        if e["event_type"] == "ZONE_DWELL" and e["zone_id"]:
            zone_dwells[e["zone_id"]].append(e["dwell_ms"])

    if not zone_frequency:
        return HeatmapResponse(zones=[])

    max_freq = max(zone_frequency.values()) if zone_frequency else 1

    zones = []
    for zone_id in sorted(zone_frequency.keys()):
        freq = zone_frequency[zone_id]
        dwells = zone_dwells.get(zone_id, [])
        avg_dwell = round(sum(dwells) / len(dwells), 2) if dwells else 0.0
        normalised = round((freq / max_freq) * 100, 2) if max_freq > 0 else 0.0

        zones.append(
            HeatmapZone(
                zone_id=zone_id,
                frequency=freq,
                avg_dwell_ms=avg_dwell,
                normalized_score=normalised,
            )
        )

    return HeatmapResponse(zones=zones)


# ---------------------------------------------------------------------------
# Anomaly Detection Endpoint
# ---------------------------------------------------------------------------

@router.get("/stores/{store_id}/anomalies", response_model=AnomalyResponse)
async def get_store_anomalies(store_id: str):
    """
    Detect anomalies for a given store:
    1. Queue Spike    – current queue depth exceeds threshold
    2. Conversion Drop – conversion rate below threshold
    3. Dead Zone      – zones with very low traffic
    """
    events = fetch_non_staff_events(store_id)
    anomalies: list[AnomalyItem] = []
    now = datetime.utcnow().isoformat()

    if not events:
        return AnomalyResponse(anomalies=[])

    # ---- 1. Queue Spike ----
    queue_in: set[str] = set()
    for e in events:
        vid = e["visitor_id"]
        if e["event_type"] == "BILLING_QUEUE_JOIN":
            queue_in.add(vid)
        elif e["event_type"] in ("BILLING_QUEUE_ABANDON", "EXIT"):
            queue_in.discard(vid)

    queue_depth = len(queue_in)
    if queue_depth > QUEUE_SPIKE_THRESHOLD:
        anomalies.append(
            AnomalyItem(
                anomaly_type="QUEUE_SPIKE",
                severity=Severity.CRITICAL,
                description=(
                    f"Billing queue depth is {queue_depth}, "
                    f"exceeding threshold of {QUEUE_SPIKE_THRESHOLD}."
                ),
                suggested_action=(
                    "Open additional billing counters or deploy staff to "
                    "manage the queue."
                ),
                detected_at=now,
            )
        )

    # ---- 2. Conversion Drop ----
    visitor_ids = {e["visitor_id"] for e in events
                   if e["event_type"] in ("ENTRY", "REENTRY")}
    billing_joiners = {e["visitor_id"] for e in events
                       if e["event_type"] == "BILLING_QUEUE_JOIN"}
    billing_abandoners = {e["visitor_id"] for e in events
                          if e["event_type"] == "BILLING_QUEUE_ABANDON"}
    purchasers = billing_joiners - billing_abandoners
    unique_visitors = len(visitor_ids)
    conversion_rate = (
        len(purchasers) / unique_visitors if unique_visitors > 0 else 0.0
    )

    if unique_visitors > 0 and conversion_rate < CONVERSION_DROP_THRESHOLD:
        anomalies.append(
            AnomalyItem(
                anomaly_type="CONVERSION_DROP",
                severity=Severity.WARN,
                description=(
                    f"Conversion rate is {conversion_rate:.2%}, "
                    f"below threshold of {CONVERSION_DROP_THRESHOLD:.0%}."
                ),
                suggested_action=(
                    "Review store layout, staff engagement, and product "
                    "placement to improve visitor-to-purchase conversion."
                ),
                detected_at=now,
            )
        )

    # ---- 3. Dead Zone ----
    zone_frequency: dict[str, int] = defaultdict(int)
    for e in events:
        if e["event_type"] == "ZONE_ENTER" and e["zone_id"]:
            zone_frequency[e["zone_id"]] += 1

    # Also collect known zones from ZONE_DWELL / ZONE_EXIT
    all_zones: set[str] = set()
    for e in events:
        if e["zone_id"]:
            all_zones.add(e["zone_id"])

    for zone_id in all_zones:
        freq = zone_frequency.get(zone_id, 0)
        if freq < DEAD_ZONE_THRESHOLD:
            anomalies.append(
                AnomalyItem(
                    anomaly_type="DEAD_ZONE",
                    severity=Severity.INFO,
                    description=(
                        f"Zone '{zone_id}' has very low traffic "
                        f"({freq} visits)."
                    ),
                    suggested_action=(
                        f"Consider repositioning high-demand products into "
                        f"zone '{zone_id}' or improving signage to direct "
                        f"foot traffic."
                    ),
                    detected_at=now,
                )
            )

    return AnomalyResponse(anomalies=anomalies)
