"""
emit.py - Event generation and emission for the Store Intelligence System.

Takes tracked persons and generates semantic events:
    ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL,
    BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY

Events are POSTed to the FastAPI ingestion endpoint.

Zone Configuration:
    Zones are defined as rectangular regions in the frame. Each zone has a name
    and coordinates. The billing zone is treated specially for queue detection.

Usage:
    python -m pipeline.emit --video path/to/video.mp4 --store_id ST1008
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import cv2
import numpy as np
import requests

from pipeline.detect import PersonDetector
from pipeline.tracker import ByteTracker, Track

logger = logging.getLogger("store_intelligence.pipeline")

# ---------------------------------------------------------------------------
# Zone Configuration
# ---------------------------------------------------------------------------

@dataclass
class Zone:
    """A named rectangular region in the camera frame."""
    zone_id: str
    x1: float  # Normalised coordinates (0-1)
    y1: float
    x2: float
    y2: float
    is_billing: bool = False

    def contains(self, cx: float, cy: float, frame_w: int, frame_h: int) -> bool:
        """Check if a point (in pixel coords) is inside this zone."""
        nx = cx / frame_w
        ny = cy / frame_h
        return self.x1 <= nx <= self.x2 and self.y1 <= ny <= self.y2


# Default zone layout for a typical retail store
# These can be overridden via configuration
DEFAULT_ZONES = [
    Zone("entrance",    0.0,  0.0,  0.25, 1.0, is_billing=False),
    Zone("zone_a",      0.25, 0.0,  0.50, 0.5, is_billing=False),
    Zone("zone_b",      0.25, 0.5,  0.50, 1.0, is_billing=False),
    Zone("zone_c",      0.50, 0.0,  0.75, 0.5, is_billing=False),
    Zone("zone_d",      0.50, 0.5,  0.75, 1.0, is_billing=False),
    Zone("billing",     0.75, 0.0,  1.0,  1.0, is_billing=True),
]

# Entry/exit detection by frame edge proximity
ENTRY_EXIT_MARGIN = 0.10  # 10% of frame width from edges


# ---------------------------------------------------------------------------
# Visitor State Tracking
# ---------------------------------------------------------------------------

@dataclass
class VisitorState:
    """Tracks the state of a single visitor across frames."""
    visitor_id: str
    track_id: int
    current_zones: set[str] = field(default_factory=set)
    zone_enter_times: dict[str, float] = field(default_factory=dict)
    in_billing_queue: bool = False
    has_entered: bool = False
    has_exited: bool = False
    entry_count: int = 0
    last_seen_time: float = 0.0
    first_seen_time: float = 0.0


# ---------------------------------------------------------------------------
# Event Emitter
# ---------------------------------------------------------------------------

class EventEmitter:
    """
    Generates semantic events from tracked person positions.

    Manages visitor state and emits events when state transitions occur
    (entering/exiting zones, joining/abandoning billing queue, etc.).
    """

    def __init__(
        self,
        store_id: str,
        camera_id: str,
        api_url: str = "http://localhost:8000",
        zones: Optional[list[Zone]] = None,
    ):
        self.store_id = store_id
        self.camera_id = camera_id
        self.api_url = api_url.rstrip("/")
        self.zones = zones or DEFAULT_ZONES

        self._visitors: dict[int, VisitorState] = {}  # track_id -> state
        self._exited: dict[str, VisitorState] = {}     # visitor_id -> state (for reentry)
        self._event_buffer: list[dict] = []
        self._frame_count = 0

    def process_tracks(
        self,
        tracks: list[Track],
        frame_w: int,
        frame_h: int,
        timestamp: Optional[str] = None,
    ) -> list[dict]:
        """
        Process tracked persons and generate events.

        Args:
            tracks: Active tracks from the ByteTracker.
            frame_w: Frame width in pixels.
            frame_h: Frame height in pixels.
            timestamp: ISO-8601 timestamp. Defaults to current UTC time.

        Returns:
            List of generated events (dicts).
        """
        self._frame_count += 1
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        current_time = time.time()
        events: list[dict] = []

        active_track_ids = {t.track_id for t in tracks}

        # Check for EXIT events (tracks that disappeared)
        exited_ids = [
            tid for tid in self._visitors if tid not in active_track_ids
        ]
        for tid in exited_ids:
            visitor = self._visitors.pop(tid)
            visitor.has_exited = True

            # If they were in the billing queue, emit BILLING_QUEUE_ABANDON
            if visitor.in_billing_queue:
                events.append(self._make_event(
                    visitor, "BILLING_QUEUE_ABANDON", ts, zone_id="billing",
                ))

            # Emit EXIT
            events.append(self._make_event(visitor, "EXIT", ts))
            self._exited[visitor.visitor_id] = visitor

        # Process active tracks
        for track in tracks:
            cx, cy = track.center

            if track.track_id not in self._visitors:
                # New track - check if this is a re-entry
                visitor_id = f"V-{track.track_id:04d}"
                is_reentry = False

                # Check re-entry: if a previously exited visitor re-appears
                # near the entrance zone
                for zone in self.zones:
                    if zone.zone_id == "entrance" and zone.contains(cx, cy, frame_w, frame_h):
                        # Check if a previous visitor was near this location
                        is_reentry = len(self._exited) > 0

                visitor = VisitorState(
                    visitor_id=visitor_id,
                    track_id=track.track_id,
                    first_seen_time=current_time,
                    last_seen_time=current_time,
                )
                self._visitors[track.track_id] = visitor

                if is_reentry:
                    visitor.entry_count = 2
                    events.append(self._make_event(
                        visitor, "REENTRY", ts, confidence=track.confidence,
                    ))
                else:
                    visitor.has_entered = True
                    visitor.entry_count = 1
                    events.append(self._make_event(
                        visitor, "ENTRY", ts, confidence=track.confidence,
                    ))
            else:
                visitor = self._visitors[track.track_id]
                visitor.last_seen_time = current_time

            # --- Zone detection ---
            new_zones: set[str] = set()
            for zone in self.zones:
                if zone.contains(cx, cy, frame_w, frame_h):
                    new_zones.add(zone.zone_id)

            # ZONE_ENTER events
            entered_zones = new_zones - visitor.current_zones
            for z in entered_zones:
                visitor.zone_enter_times[z] = current_time
                events.append(self._make_event(
                    visitor, "ZONE_ENTER", ts, zone_id=z,
                    confidence=track.confidence,
                ))

                # Check billing queue
                zone_obj = self._get_zone(z)
                if zone_obj and zone_obj.is_billing and not visitor.in_billing_queue:
                    visitor.in_billing_queue = True
                    events.append(self._make_event(
                        visitor, "BILLING_QUEUE_JOIN", ts, zone_id=z,
                        confidence=track.confidence,
                    ))

            # ZONE_EXIT events
            exited_zones = visitor.current_zones - new_zones
            for z in exited_zones:
                dwell_ms = 0
                if z in visitor.zone_enter_times:
                    dwell_ms = int((current_time - visitor.zone_enter_times[z]) * 1000)
                    # Emit ZONE_DWELL before ZONE_EXIT
                    events.append(self._make_event(
                        visitor, "ZONE_DWELL", ts, zone_id=z,
                        dwell_ms=dwell_ms, confidence=track.confidence,
                    ))
                    del visitor.zone_enter_times[z]

                events.append(self._make_event(
                    visitor, "ZONE_EXIT", ts, zone_id=z,
                    dwell_ms=dwell_ms, confidence=track.confidence,
                ))

                # Billing queue abandon check
                zone_obj = self._get_zone(z)
                if zone_obj and zone_obj.is_billing and visitor.in_billing_queue:
                    visitor.in_billing_queue = False
                    events.append(self._make_event(
                        visitor, "BILLING_QUEUE_ABANDON", ts, zone_id=z,
                        confidence=track.confidence,
                    ))

            visitor.current_zones = new_zones

        return events

    def _make_event(
        self,
        visitor: VisitorState,
        event_type: str,
        timestamp: str,
        zone_id: str = "",
        dwell_ms: int = 0,
        confidence: float = 0.0,
    ) -> dict:
        """Create an event dict matching the EventPayload schema."""
        return {
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": self.camera_id,
            "visitor_id": visitor.visitor_id,
            "event_type": event_type,
            "timestamp": timestamp,
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "is_staff": False,
            "confidence": round(confidence, 4),
            "metadata": {
                "track_id": visitor.track_id,
                "entry_count": visitor.entry_count,
                "frame": self._frame_count,
            },
        }

    def _get_zone(self, zone_id: str) -> Optional[Zone]:
        """Look up a zone by ID."""
        for z in self.zones:
            if z.zone_id == zone_id:
                return z
        return None

    def flush_events(self, events: list[dict]) -> bool:
        """
        POST events to the FastAPI ingestion endpoint.

        Returns True if successful, False otherwise.
        """
        if not events:
            return True

        url = f"{self.api_url}/events/ingest"
        payload = {"events": events}

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            result = response.json()
            logger.info(
                "events_flushed",
                extra={
                    "accepted": result.get("accepted", 0),
                    "duplicates": result.get("duplicates", 0),
                    "total": result.get("total", 0),
                },
            )
            return True
        except requests.exceptions.ConnectionError:
            logger.warning(
                "api_connection_failed",
                extra={"url": url, "event_count": len(events)},
            )
            return False
        except Exception as e:
            logger.error(
                "event_flush_failed",
                extra={"error": str(e), "event_count": len(events)},
            )
            return False


# ---------------------------------------------------------------------------
# Pipeline Runner
# ---------------------------------------------------------------------------

def run_pipeline(
    video_path: str,
    store_id: str,
    camera_id: str,
    api_url: str = "http://localhost:8000",
    frame_skip: int = 5,
    confidence_threshold: float = 0.35,
    max_frames: Optional[int] = None,
) -> dict:
    """
    Run the full detection → tracking → event pipeline on a video file.

    Args:
        video_path: Path to the video file.
        store_id: Store identifier.
        camera_id: Camera identifier.
        api_url: FastAPI server URL.
        frame_skip: Process every Nth frame.
        confidence_threshold: Detection confidence threshold.
        max_frames: Maximum frames to process (None = all).

    Returns:
        Summary dict with processing stats.
    """
    logger.info(
        "pipeline_start",
        extra={"video": video_path, "store_id": store_id, "camera_id": camera_id},
    )

    # Initialise components
    detector = PersonDetector(confidence_threshold=confidence_threshold)
    tracker = ByteTracker()
    emitter = EventEmitter(
        store_id=store_id,
        camera_id=camera_id,
        api_url=api_url,
    )

    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    logger.info(
        "video_info",
        extra={
            "fps": fps, "total_frames": total_frames,
            "resolution": f"{frame_w}x{frame_h}",
        },
    )

    frame_num = 0
    processed = 0
    total_events = 0
    all_events: list[dict] = []

    start_time = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_num += 1

        if max_frames and frame_num > max_frames:
            break

        # Skip frames for performance
        if frame_num % frame_skip != 0:
            continue

        processed += 1

        # Compute timestamp from frame number
        frame_ts = datetime.now(timezone.utc).isoformat()

        # Detect persons
        detections = detector.detect(frame)

        # Update tracker
        tracks = tracker.update(detections)

        # Generate events
        if tracks:
            events = emitter.process_tracks(tracks, frame_w, frame_h, frame_ts)
            if events:
                all_events.extend(events)
                total_events += len(events)

        # Flush events in batches of 50
        if len(all_events) >= 50:
            emitter.flush_events(all_events)
            all_events.clear()

        # Progress logging every 100 processed frames
        if processed % 100 == 0:
            elapsed = time.time() - start_time
            logger.info(
                "pipeline_progress",
                extra={
                    "frame": frame_num,
                    "processed": processed,
                    "total_frames": total_frames,
                    "events": total_events,
                    "elapsed_s": round(elapsed, 1),
                },
            )

    # Flush remaining events
    if all_events:
        emitter.flush_events(all_events)

    cap.release()

    elapsed = time.time() - start_time
    summary = {
        "video": video_path,
        "store_id": store_id,
        "camera_id": camera_id,
        "total_frames": total_frames,
        "processed_frames": processed,
        "total_events": total_events,
        "elapsed_seconds": round(elapsed, 2),
        "fps_processed": round(processed / elapsed, 2) if elapsed > 0 else 0,
    }

    logger.info("pipeline_complete", extra=summary)
    return summary


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    """Command-line interface for the event emission pipeline."""
    parser = argparse.ArgumentParser(
        description="Store Intelligence - Event Emission Pipeline"
    )
    parser.add_argument("--video", required=True, help="Path to video file")
    parser.add_argument("--store_id", default="ST1008", help="Store ID")
    parser.add_argument("--camera_id", default="CAM1", help="Camera ID")
    parser.add_argument("--api_url", default="http://localhost:8000", help="API URL")
    parser.add_argument("--frame_skip", type=int, default=5, help="Process every Nth frame")
    parser.add_argument("--confidence", type=float, default=0.35, help="Detection confidence")
    parser.add_argument("--max_frames", type=int, default=None, help="Max frames to process")

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    summary = run_pipeline(
        video_path=args.video,
        store_id=args.store_id,
        camera_id=args.camera_id,
        api_url=args.api_url,
        frame_skip=args.frame_skip,
        confidence_threshold=args.confidence,
        max_frames=args.max_frames,
    )

    print("\n=== Pipeline Summary ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
