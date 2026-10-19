from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import current_user
from app.db import Base, get_db
from app.main import app
from app.models import (
    Alert,
    InventoryItem,
    Match,
    MonitoringNotification,
    Pharmacy,
)
from app.notification_service import sync_notifications


@pytest.fixture
def notification_api():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    identity = {"user": "notification-a"}

    def db_override():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[current_user] = lambda: identity["user"]
    client = TestClient(app)
    try:
        yield client, sessions, identity
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _seed_two_pharmacies(sessions):
    with sessions() as db:
        pharmacy_a = Pharmacy(owner_id="notification-a", name="Pharmacy A")
        pharmacy_b = Pharmacy(owner_id="notification-b", name="Pharmacy B")
        db.add_all([pharmacy_a, pharmacy_b])
        db.flush()
        alert = Alert(
            fingerprint=uuid4().hex,
            product_name="Linezolid Tablets IP 600mg",
            manufacturer="Demo Manufacturer",
            batch_number="TEST-001",
            quality_issue="Synthetic test finding",
            reporting_period="AUG-2026",
            reporting_source="Test source",
            source_url="https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug",
            run_id="test-run",
            raw_record={"synthetic": True},
        )
        db.add(alert)
        db.flush()
        items = []
        matches = []
        for pharmacy in (pharmacy_a, pharmacy_b):
            item = InventoryItem(
                pharmacy_id=pharmacy.id,
                medicine_name=alert.product_name,
                manufacturer="Demo Manufacturer",
                batch_number="TEST-001",
                strength="600mg",
                quantity=1,
            )
            db.add(item)
            items.append(item)
        db.flush()
        for pharmacy, item in zip((pharmacy_a, pharmacy_b), items):
            match = Match(
                pharmacy_id=pharmacy.id,
                inventory_id=item.id,
                alert_id=alert.fingerprint,
                status="potential_match",
                explanation={"synthetic_test": True},
            )
            db.add(match)
            matches.append(match)
        db.commit()
        return pharmacy_a.id, pharmacy_b.id, alert.fingerprint, [item.id for item in items], [match.id for match in matches]


def test_notifications_are_tenant_scoped_malformed_ids_are_safe_and_reads_are_idempotent(notification_api):
    client, sessions, identity = notification_api
    pharmacy_a, pharmacy_b, alert_id, item_ids, _ = _seed_two_pharmacies(sessions)
    with sessions() as db:
        db.add(MonitoringNotification(
            pharmacy_id=pharmacy_b,
            event_id="private-event",
            inventory_id=item_ids[1],
            alert_id=alert_id,
            status="potential_match",
            title="Private pharmacy notification",
            message="Confidential fixture content",
        ))
        db.commit()
        notification_id = db.scalar(select(MonitoringNotification.id))

    response = client.get("/api/notifications")
    assert response.status_code == 200
    assert response.json() == []
    cross_tenant = client.patch(f"/api/notifications/{notification_id}/read")
    assert cross_tenant.status_code == 404
    assert "Confidential" not in cross_tenant.text
    assert client.patch("/api/notifications/not-a-valid-id/read").status_code == 404
    assert client.get("/api/dashboard").json()["unread_notifications"] == 0

    identity["user"] = "notification-b"
    listed = client.get("/api/notifications")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    notice = listed.json()[0]
    assert notice["reporting_period"] == "AUG-2026"
    assert notice["source_url"].startswith("https://cdscoonline.gov.in/")
    assert client.get("/api/dashboard").json()["unread_notifications"] == 1

    first = client.patch(f"/api/notifications/{notification_id}/read")
    second = client.patch(f"/api/notifications/{notification_id}/read")
    assert first.status_code == second.status_code == 200
    assert first.json()["is_read"] is second.json()["is_read"] is True
    assert client.get("/api/dashboard").json()["unread_notifications"] == 0
    with sessions() as db:
        stored = db.get(MonitoringNotification, notification_id)
        assert stored.is_read is True
        assert stored.pharmacy_id == pharmacy_b


def test_sync_notifications_deduplicates_by_pharmacy_and_preserves_acknowledgement(notification_api):
    _, sessions, _ = notification_api
    pharmacy_a_id, pharmacy_b_id, _, _, match_ids = _seed_two_pharmacies(sessions)
    with sessions() as db:
        pharmacy_a = db.get(Pharmacy, pharmacy_a_id)
        pharmacy_b = db.get(Pharmacy, pharmacy_b_id)
        assert sync_notifications(db, pharmacy_a)["created"] == 1
        assert sync_notifications(db, pharmacy_b)["created"] == 1
        assert sync_notifications(db, pharmacy_a)["created"] == 0
        assert sync_notifications(db, pharmacy_a)["skipped"] == 1
        notices = db.scalars(select(MonitoringNotification).order_by(MonitoringNotification.pharmacy_id)).all()
        assert len(notices) == 2
        own = next(value for value in notices if value.pharmacy_id == pharmacy_a_id)
        own.is_read = True
        db.commit()

        unchanged = sync_notifications(db, pharmacy_a)
        db.commit()
        assert unchanged["created"] == 0
        assert db.get(MonitoringNotification, own.id).is_read is True

        match = db.get(Match, match_ids[0])
        alert = db.get(Alert, match.alert_id)
        alert.quality_issue = "Revised synthetic finding"
        result = sync_notifications(db, pharmacy_a)
        db.commit()
        assert result["created"] == 1
        assert result["deactivated"] == 1
        active = db.scalars(select(MonitoringNotification).where(
            MonitoringNotification.pharmacy_id == pharmacy_a_id,
            MonitoringNotification.is_active.is_(True),
        )).all()
        inactive = db.scalars(select(MonitoringNotification).where(
            MonitoringNotification.pharmacy_id == pharmacy_a_id,
            MonitoringNotification.is_active.is_(False),
        )).all()
        assert len(active) == len(inactive) == 1
        assert inactive[0].is_read is True
        assert active[0].is_read is False
        assert db.scalar(select(func.count()).select_from(MonitoringNotification).where(
            MonitoringNotification.pharmacy_id == pharmacy_b_id,
            MonitoringNotification.is_active.is_(True),
        )) == 1


def test_repeated_authenticated_match_rechecks_do_not_duplicate_notifications(notification_api):
    client, sessions, _ = notification_api
    pharmacy_a_id, _, _, _, _ = _seed_two_pharmacies(sessions)
    assert client.post("/api/matches/recheck").status_code == 200
    assert client.post("/api/matches/recheck").status_code == 200
    response = client.get("/api/notifications")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert client.get("/api/dashboard").json()["unread_notifications"] == 1
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(MonitoringNotification).where(
            MonitoringNotification.pharmacy_id == pharmacy_a_id,
        )) == 1


def test_sync_deactivates_notification_when_match_is_removed(notification_api):
    _, sessions, _ = notification_api
    pharmacy_a_id, _, _, _, match_ids = _seed_two_pharmacies(sessions)
    with sessions() as db:
        pharmacy = db.get(Pharmacy, pharmacy_a_id)
        sync_notifications(db, pharmacy)
        match = db.get(Match, match_ids[0])
        match.status = "no_identified_match"
        db.flush()
        result = sync_notifications(db, pharmacy)
        db.commit()
        notice = db.scalar(select(MonitoringNotification).where(
            MonitoringNotification.pharmacy_id == pharmacy_a_id,
        ))
        assert result["deactivated"] == 1
        assert notice.is_active is False
