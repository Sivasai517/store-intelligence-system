"""
test_metrics.py - Tests for the metrics and funnel endpoints.
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
    """Create a unique database for each test and return its path."""
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
    confidence: float = 0.9,
) -> dict:
    """Helper to create a test event payload."""
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
        "confidence": confidence,
        "metadata": {},
    }


def ingest_events(client: TestClient, events: list[dict]):
    """Helper to ingest a list of events via the API."""
    response = client.post("/events/ingest", json={"events": events})
    assert response.status_code == 200
    return response.json()


class TestEmptyStore:
    def test_metrics_empty(self, test_client):
        response = test_client.get("/stores/EMPTY001/metrics")
        data = response.json()
        assert data["unique_visitors"] == 0
        assert data["conversion_rate"] == 0.0

    def test_funnel_empty(self, test_client):
        response = test_client.get("/stores/EMPTY001/funnel")
        assert all(stage["count"] == 0 for stage in response.json()["stages"])

    def test_heatmap_empty(self, test_client):
        response = test_client.get("/stores/EMPTY001/heatmap")
        assert response.json()["zones"] == []


class TestIngestion:
    def test_single_event(self, test_client):
        event = make_event()
        result = ingest_events(test_client, [event])
        assert result["accepted"] == 1

    def test_duplicate_event(self, test_client):
        event = make_event()
        ingest_events(test_client, [event])
        result = ingest_events(test_client, [event])
        assert result["duplicates"] == 1


class TestMetrics:
    def test_unique_visitors_count(self, test_client):
        events = [
            make_event(visitor_id="V-0001", event_type="ENTRY"),
            make_event(visitor_id="V-0002", event_type="ENTRY"),
        ]
        ingest_events(test_client, events)
        response = test_client.get("/stores/TEST001/metrics")
        assert response.json()["unique_visitors"] == 2

    def test_conversion_rate(self, test_client):
        events = [
            make_event(visitor_id="V-0001", event_type="ENTRY"),
            make_event(visitor_id="V-0001", event_type="BILLING_QUEUE_JOIN"),
            make_event(visitor_id="V-0002", event_type="ENTRY"),
        ]
        ingest_events(test_client, events)
        data = test_client.get("/stores/TEST001/metrics").json()
        assert data["conversion_rate"] == 0.5

    def test_avg_dwell_time(self, test_client):
        events = [
            make_event(visitor_id="V-0001", event_type="ZONE_DWELL", zone_id="a", dwell_ms=1000),
            make_event(visitor_id="V-0002", event_type="ZONE_DWELL", zone_id="a", dwell_ms=3000),
        ]
        ingest_events(test_client, events)
        data = test_client.get("/stores/TEST001/metrics").json()
        assert data["avg_dwell_time"]["a"] == 2000.0

    def test_queue_depth(self, test_client):
        events = [
            make_event(visitor_id="V-0001", event_type="BILLING_QUEUE_JOIN"),
            make_event(visitor_id="V-0002", event_type="BILLING_QUEUE_JOIN"),
            make_event(visitor_id="V-0001", event_type="EXIT"),
        ]
        ingest_events(test_client, events)
        data = test_client.get("/stores/TEST001/metrics").json()
        assert data["queue_depth"] == 1


class TestReentry:
    def test_reentry_counts_as_visitor(self, test_client):
        events = [
            make_event(visitor_id="V-0001", event_type="ENTRY"),
            make_event(visitor_id="V-0001", event_type="REENTRY"),
        ]
        ingest_events(test_client, events)
        data = test_client.get("/stores/TEST001/metrics").json()
        assert data["unique_visitors"] == 1

    def test_reentry_in_funnel(self, test_client):
        events = [
            make_event(visitor_id="V-0001", event_type="ENTRY"),
            make_event(visitor_id="V-0001", event_type="ZONE_ENTER", zone_id="a"),
            make_event(visitor_id="V-0001", event_type="REENTRY"),
        ]
        ingest_events(test_client, events)
        data = test_client.get("/stores/TEST001/funnel").json()
        entry_stage = next(s for s in data["stages"] if s["stage"] == "Entry")
        assert entry_stage["count"] == 1


class TestHealth:
    def test_health_ok(self, test_client):
        response = test_client.get("/health")
        assert response.json()["status"] == "healthy"
