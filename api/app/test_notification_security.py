
"""Test pharmacy notification access isolation."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import Base, get_db
from app.main import app
from app.models import (
    Alert,
    InventoryItem,
    MonitoringNotification,
    Pharmacy,
)

# Isolated in-memory database
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

Base.metadata.create_all(engine)

active_user = {"id": "security-test-a"}

def fake_user():
    return active_user["id"]

def fake_db():
    with Session(engine) as db:
        yield db

app.dependency_overrides[current_user] = fake_user
app.dependency_overrides[get_db] = fake_db

try:
    with Session(engine) as db:
        a = Pharmacy(owner_id="security-test-a", name="Pharmacy A")
        b = Pharmacy(owner_id="security-test-b", name="Pharmacy B")
        db.add_all([a, b])
        db.flush()

        alert = Alert(
            fingerprint=uuid4().hex,
            product_name="Linezolid 600mg",
            manufacturer="Demo Manufacturer",
            batch_number="TEST-001",
            quality_issue="Synthetic test finding",
            reporting_period="AUG-2026",
            reporting_source="Test",
            source_url="https://cdscoonline.gov.in/",
            run_id="security-test",
            raw_record={"synthetic": True},
        )
        db.add(alert)

        item = InventoryItem(
            pharmacy_id=b.id,
            medicine_name="Linezolid 600mg",
            manufacturer="Demo Manufacturer",
            batch_number="TEST-001",
            strength="600mg",
            quantity=1,
        )
        db.add(item)
        db.flush()

        notification = MonitoringNotification(
            pharmacy_id=b.id,
            event_id=uuid4().hex,
            inventory_id=item.id,
            alert_id=alert.fingerprint,
            status="potential_match",
            title="Pharmacy B confidential notification",
            message="Synthetic security test",
        )
        db.add(notification)
        db.commit()
        notification_id = notification.id

    with TestClient(app) as client:
        # Pharmacy A must not see Pharmacy B's notifications
        active_user["id"] = "security-test-a"
        response = client.get("/api/notifications")
        assert response.status_code == 200, response.text
        assert response.json() == []

        response = client.patch(
            f"/api/notifications/{notification_id}/read"
        )
        assert response.status_code == 404, response.text

        # Pharmacy B should see and update its own notification
        active_user["id"] = "security-test-b"
        response = client.get("/api/notifications")
        assert response.status_code == 200, response.text
        assert len(response.json()) == 1

        response = client.patch(
            f"/api/notifications/{notification_id}/read"
        )
        assert response.status_code == 200, response.text
        assert response.json()["is_read"] is True

        print("PASS: Pharmacy A cannot list Pharmacy B's notifications")
        print("PASS: Pharmacy A cannot mark Pharmacy B's notification as read")
        print("PASS: Pharmacy B can access and update its notification")
        print("All notification API security tests passed.")

finally:
    app.dependency_overrides.clear()
    engine.dispose()
