"""
test_anomalies.py - Tests for anomaly detection and heatmap endpoints.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
import uuid
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models import init_db


@pytest.fixture
def test_db():
    """Create a unique database for each test."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.environ["DATABASE_PATH"] = path
    init_db()
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def test_client(test_db):
    """Return a fresh test client for each test."""
    from app.main import app
    with TestClient(app) as c:
        yield c


def make_event(
    store_id: str = "TEST001",
    visitor_id: str = "V-0001",
    event_type: str = "ENTRY",
    zone_id: str = "",
    dwell_ms: int = 0,
    is_staff: bool = False,
) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "store_id": store_id,
        "camera_id": "CAM1",
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp": datetime.utcnow().isoformat(),
        "zone_id": zone_id,
        "dwell_ms": dwell_ms,
        "is_staff": is_staff,
        "confidence": 0.9,
        "metadata": {},
    }


def ingest_events(client: TestClient, events: list[dict]):
    response = client.post("/events/ingest", json={"events": events})
    assert response.status_code == 200
    return response.json()


class TestQueueSpike:
    def test_queue_spike_detected(self, test_client):
        events = []
        for i in range(10):
            vid = f"V-{i:04d}"
            events.append(make_event(visitor_id=vid, event_type="BILLING_QUEUE_JOIN"))
        ingest_events(test_client, events)
        data = test_client.get("/stores/TEST001/anomalies").json()
        assert any(a["anomaly_type"] == "QUEUE_SPIKE" for a in data["anomalies"])


class TestHeatmap:
    def test_heatmap_normalized_score(self, test_client):
        events = []
        for i in range(10):
            events.append(make_event(visitor_id=f"V-{i}", event_type="ZONE_ENTER", zone_id="busy"))
        for i in range(5):
            events.append(make_event(visitor_id=f"V-{i+10}", event_type="ZONE_ENTER", zone_id="quiet"))
        ingest_events(test_client, events)
        data = test_client.get("/stores/TEST001/heatmap").json()
        zones = {z["zone_id"]: z for z in data["zones"]}
        assert zones["busy"]["normalized_score"] == 100.0
        assert zones["quiet"]["normalized_score"] == 50.0
