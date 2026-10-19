from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base
from app.ingest_service import sync_once
from app.main import ingestion_status
from app.models import Alert, AlertVersion, IngestionRun, InventoryItem, Match, MonitoringNotification, Pharmacy
from app.tinyfish import normalize_record


@pytest.fixture
def session():
    local_engine = create_engine("sqlite://")
    Base.metadata.create_all(local_engine)
    with Session(local_engine, expire_on_commit=False) as db:
        yield db
    local_engine.dispose()


def source(issue="Synthetic dissolution finding"):
    return normalize_record({"product_name": "Linezolid Tablets IP 600mg", "manufacturer": "Example Labs",
        "batch_number": "OFFLINE-123", "quality_issue": issue, "reporting_period": "AUG-2026"}, "AUG-2026")


def test_disabled_schedule_cannot_invoke_provider_or_create_run(session):
    from app.scheduled_ingest import SchedulePolicy, run_scheduled
    def forbidden(*_):
        pytest.fail("disabled schedule invoked provider")
    assert run_scheduled(session, SchedulePolicy(), "", "AUG-2026", provider=forbidden) == {"state": "disabled"}
    assert session.query(IngestionRun).count() == 0


@pytest.mark.parametrize("kwargs", [{"max_requests": 0}, {"max_requests": 3}, {"max_records": 0},
    {"max_records": 26}, {"interval_hours": 5}, {"interval_hours": 169}])
def test_policy_bounds_fail_before_any_call(kwargs):
    from app.scheduled_ingest import SchedulePolicy
    with pytest.raises(ValueError):
        SchedulePolicy(**kwargs)


def test_local_file_lock_prevents_overlap_and_releases(tmp_path):
    from app.ingest_service import operator_lock
    local_engine = create_engine("sqlite:///" + (tmp_path / "isolated.db").as_posix())
    try:
        with operator_lock(local_engine):
            with pytest.raises(RuntimeError, match="Another regulatory"):
                with operator_lock(local_engine):
                    pytest.fail("overlapping synchronization acquired local lock")
        with operator_lock(local_engine):
            pass
    finally:
        local_engine.dispose()


def test_playback_entrypoint_never_retrieves_or_changes_demo(monkeypatch):
    from app import scheduled_ingest
    monkeypatch.setattr(scheduled_ingest, "retrieve", lambda *_: pytest.fail("playback used provider"))
    result = scheduled_ingest.playback()
    assert result == {"state": "offline_playback", "source_kind": "historical_snapshot",
        "records": 5, "repeat_inserted": 0, "provider_requests": 0}


def test_env_boolean_is_strict_and_defaults_off(monkeypatch):
    from app.scheduled_ingest import SchedulePolicy
    monkeypatch.delenv("PHARMAONE_SCHEDULE_ENABLED", raising=False)
    assert SchedulePolicy.from_env().enabled is False
    monkeypatch.setenv("PHARMAONE_SCHEDULE_ENABLED", "yes-maybe")
    with pytest.raises(ValueError):
        SchedulePolicy.from_env()


def test_schedule_throttles_success_failure_and_other_periods(session):
    from app.scheduled_ingest import SchedulePolicy, run_scheduled
    policy = SchedulePolicy(enabled=True)
    calls = []
    now = datetime.now(timezone.utc)
    def provider(*_):
        calls.append(1)
        return [source()], "synthetic-offline-run"
    first = run_scheduled(session, policy, "synthetic-test-key", "AUG-2026", provider=provider, now=now)
    assert first["state"] == "succeeded"
    assert run_scheduled(session, policy, "synthetic-test-key", "SEP-2026", provider=provider, now=now)["state"] == "not_due"
    assert len(calls) == 1
    def fail(*_):
        calls.append(1)
        raise RuntimeError("private provider error")
    later = now + timedelta(hours=24)
    with pytest.raises(RuntimeError):
        run_scheduled(session, policy, "synthetic-test-key", "AUG-2026", provider=fail, now=later)
    assert run_scheduled(session, policy, "synthetic-test-key", "AUG-2026", provider=provider, now=later)["state"] == "not_due"
    assert session.query(Alert).count() == 1
    assert "private" not in session.scalars(select(IngestionRun).where(IngestionRun.status == "failed")).one().error
    assert len(calls) == 2


@pytest.mark.parametrize("budget", [1, 2])
def test_429_retry_never_exceeds_explicit_request_budget(session, monkeypatch, budget):
    from app import ingest_service
    monkeypatch.setattr(ingest_service.time, "sleep", lambda *_: None)
    calls = []
    def limited(*_):
        calls.append(1)
        response = httpx.Response(429, request=httpx.Request("POST", "https://provider.example.test"))
        raise httpx.HTTPStatusError("rate limited", request=response.request, response=response)
    with pytest.raises(httpx.HTTPStatusError):
        sync_once(session, "synthetic-test-key", "AUG-2026", provider=limited, max_requests=budget)
    assert len(calls) == budget
    assert session.scalars(select(IngestionRun)).one().retrieval_metadata["provider_requests"] == budget


def test_oversized_provider_result_is_rejected_not_stored(session):
    with pytest.raises(ValueError, match="record limit"):
        sync_once(session, "synthetic-test-key", "AUG-2026", 1, provider=lambda *_: ([source(), source()], "offline"))
    assert session.query(Alert).count() == 0
    assert session.scalars(select(IngestionRun)).one().status == "failed"


def test_historical_playback_repeats_revises_rematches_and_preserves_read_state(session):
    pharmacy = Pharmacy(owner_id="offline-owner", name="Offline Pharmacy")
    session.add(pharmacy)
    session.flush()
    session.add(InventoryItem(pharmacy_id=pharmacy.id, medicine_name="Linezolid Tablets IP 600mg",
        manufacturer="Example Labs", batch_number="OFFLINE-123", strength="600mg", quantity=1))
    session.commit()
    def playback(issue):
        return sync_once(session, "offline-not-a-key", "AUG-2026", 1, source_kind="historical_snapshot",
            method="offline_playback", provider=lambda *_: ([source(issue)], "offline-test-run"))
    first = playback("Synthetic dissolution finding")
    assert first.source_kind == "historical_snapshot"
    assert session.scalars(select(Match)).one().status == "potential_match"
    original = session.scalars(select(MonitoringNotification)).one()
    original.is_read = True
    session.commit()
    playback("Synthetic dissolution finding")
    assert session.query(Alert).count() == session.query(AlertVersion).count() == 1
    assert session.query(MonitoringNotification).count() == 1
    assert original.is_read is True
    playback("Synthetic revised dissolution finding")
    assert session.query(Alert).count() == 1
    assert session.query(AlertVersion).count() == 2
    notes = session.scalars(select(MonitoringNotification)).all()
    assert len(notes) == 2
    assert sum(n.is_active for n in notes) == 1
    assert sum(n.is_active and not n.is_read for n in notes) == 1
    status = ingestion_status("offline-owner", session)
    assert status["state"] == "historical_snapshot"
    assert status["last_checked"] is None
    assert status["historical_snapshot_imported"] is True
    assert status["retrieval_metadata"]["imported_as_historical"] is True


def test_malformed_inventory_strength_is_review_only_and_does_not_block_rematching(session):
    pharmacy = Pharmacy(owner_id="strength-safety-owner", name="Strength Safety Pharmacy")
    session.add(pharmacy)
    session.flush()
    malformed = InventoryItem(
        pharmacy_id=pharmacy.id,
        medicine_name="Linezolid Tablets IP 600mg",
        manufacturer="Example Labs",
        batch_number="OFFLINE-123",
        strength="600mg/0tablet",
        quantity=1,
    )
    valid = InventoryItem(
        pharmacy_id=pharmacy.id,
        medicine_name="Linezolid Tablets IP 0.6g",
        manufacturer="Example Labs",
        batch_number="OFFLINE-123",
        strength="600mg",
        quantity=1,
    )
    session.add_all([malformed, valid])
    session.commit()

    sync_once(
        session,
        "offline-not-a-key",
        "AUG-2026",
        1,
        source_kind="historical_snapshot",
        method="offline_playback",
        provider=lambda *_: ([source()], "offline-strength-safety"),
    )

    statuses = {
        match.inventory_id: match.status
        for match in session.scalars(select(Match)).all()
    }
    assert statuses[malformed.id] == "needs_verification"
    assert statuses[valid.id] == "potential_match"
