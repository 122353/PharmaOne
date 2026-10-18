from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
import pytest
from app.db import Base
from app.models import Alert, IngestionRun, Pharmacy
from app.tinyfish import normalize_record


def test_operator_sync_shares_deduplicated_alerts_and_tracks_failure():
    from app.ingest_service import sync_once
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    source = normalize_record({
        "product_name": "Synthetic Test Drug", "manufacturer": "Example Labs",
        "batch_number": "SYN123", "quality_issue": "Synthetic finding",
        "reporting_period": "AUG-2026",
    }, "AUG-2026")
    calls = []

    def provider(key, period, limit):
        calls.append((key, period, limit))
        return [source], "mock-provider"

    with Session(engine, expire_on_commit=False) as db:
        db.add(Pharmacy(owner_id="synthetic-owner", name="Synthetic Pharmacy"))
        db.commit()
        first = sync_once(db, "operator-test-key", "AUG-2026", 1, provider=provider)
        second = sync_once(db, "operator-test-key", "AUG-2026", 1, provider=provider)
        assert first.record_count == second.record_count == 1
        assert calls == [("operator-test-key", "AUG-2026", 1)] * 2
        assert db.query(Alert).count() == 1
        assert db.query(IngestionRun).count() == 2
        assert all(r.requesting_user_id is None and r.connection_id is None for r in db.scalars(select(IngestionRun)))

        def fail(*_):
            raise RuntimeError("synthetic provider secret must not leak")

        try:
            sync_once(db, "operator-test-key", "SEP-2026", 1, provider=fail)
        except RuntimeError:
            pass
        failed = db.scalar(select(IngestionRun).where(IngestionRun.period == "SEP-2026"))
        assert failed.status == "failed"
        assert "secret" not in failed.error
        assert db.query(Alert).count() == 1


def test_sync_rejects_invalid_bounds_and_empty_result_without_changing_alerts():
    from app.ingest_service import sync_once
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    calls = []

    def empty_provider(*args):
        calls.append(args)
        return [], "synthetic-run"

    with Session(engine, expire_on_commit=False) as db:
        with pytest.raises(ValueError):
            sync_once(db, "operator-test-key", "bad-period", 1, provider=empty_provider)
        with pytest.raises(ValueError):
            sync_once(db, "operator-test-key", "AUG-2026", 26, provider=empty_provider)
        assert calls == []
        assert db.query(IngestionRun).count() == 0
        with pytest.raises(RuntimeError, match="no source records"):
            sync_once(db, "operator-test-key", "AUG-2026", 1, provider=empty_provider)
        assert db.query(Alert).count() == 0
        run = db.scalar(select(IngestionRun))
        assert run.status == "failed"


def test_sync_deduplicates_records_within_one_provider_result():
    from app.ingest_service import sync_once
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    record = normalize_record({
        "product_name": "Synthetic Test Drug", "manufacturer": "Example Labs",
        "batch_number": "SYN123", "quality_issue": "Synthetic finding",
        "reporting_period": "AUG-2026",
    }, "AUG-2026")
    with Session(engine, autoflush=False, expire_on_commit=False) as db:
        sync_once(db, "operator-test-key", "AUG-2026", 2,
                  provider=lambda *_: ([record, record.copy()], "synthetic-run"))
        assert db.query(Alert).count() == 1
