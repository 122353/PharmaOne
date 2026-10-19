"""Operator one-shot scheduler entrypoint. Disabled unless explicitly configured.

Offline rehearsal: python -m app.scheduled_ingest --playback
Live (requires operator approval/configuration): python -m app.scheduled_ingest
There is deliberately no public HTTP trigger and no background loop in the API.
"""
import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import create_engine, desc, select
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, SessionLocal, engine, initialize_schema
from .ingest_service import operator_lock, sync_once
from .models import IngestionRun
from .tinyfish import retrieve


@dataclass(frozen=True)
class SchedulePolicy:
    enabled: bool = False
    max_requests: int = 1
    max_records: int = 10
    interval_hours: int = 24

    def __post_init__(self):
        if type(self.enabled) is not bool or self.max_requests not in (1, 2):
            raise ValueError("Schedule requires a boolean enable flag and 1 to 2 requests")
        if not 1 <= self.max_records <= 25 or not 6 <= self.interval_hours <= 168:
            raise ValueError("Schedule bounds: 1 to 25 records; interval 6 to 168 hours")

    @classmethod
    def from_env(cls):
        flag = os.getenv("PHARMAONE_SCHEDULE_ENABLED", "false").casefold()
        if flag not in {"true", "false"}:
            raise ValueError("PHARMAONE_SCHEDULE_ENABLED must be true or false")
        return cls(enabled=flag == "true",
                   max_requests=int(os.getenv("PHARMAONE_SCHEDULE_MAX_REQUESTS", "1")),
                   max_records=int(os.getenv("PHARMAONE_SCHEDULE_MAX_RECORDS", "10")),
                   interval_hours=int(os.getenv("PHARMAONE_SCHEDULE_INTERVAL_HOURS", "24")))


def run_scheduled(db: Session, policy: SchedulePolicy, key: str, period: str, *,
                  provider=retrieve, now: datetime | None = None) -> dict:
    if not policy.enabled:
        return {"state": "disabled"}
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Schedule time must include a timezone")
    with operator_lock(db.get_bind()):
        # A failed or interrupted paid run consumes the frequency budget too.
        # Manual source checks also suppress a scheduled check in this interval.
        latest = db.scalar(select(IngestionRun).where(
            IngestionRun.source_kind == "operator_live",
            IngestionRun.requesting_user_id.is_(None)).order_by(desc(IngestionRun.started_at)).limit(1))
        if latest:
            started = latest.started_at
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            if now < started + timedelta(hours=policy.interval_hours):
                return {"state": "not_due"}
        run = sync_once(db, key, period, policy.max_records, provider=provider,
                        max_requests=policy.max_requests, method="scheduled_tinyfish", started_at=now)
        return {"state": run.status, "run_id": run.id, "records": run.record_count}


def playback() -> dict:
    """Use the verified historical snapshot in a fresh, in-memory database."""
    from .verified_snapshot import ROOT, import_verified_snapshot
    local_engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(local_engine)
        with Session(local_engine, expire_on_commit=False) as db:
            args = (ROOT / "evidence/cdsco-aug-2026-tinyfish.json", ROOT / "evidence/cdsco-verification-report.json")
            first = import_verified_snapshot(db, *args)
            repeated = import_verified_snapshot(db, *args)
            return {"state": "offline_playback", "source_kind": "historical_snapshot",
                    "records": first, "repeat_inserted": repeated, "provider_requests": 0}
    finally:
        local_engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--playback", action="store_true")
    args = parser.parse_args()
    try:
        if args.playback:
            print(playback())
            return
        policy = SchedulePolicy.from_env()
        if not policy.enabled:
            print({"state": "disabled"})
            return
        # Local execution must resolve to the explicit project demo target.
        if settings().pharmaone_env == "local":
            root = Path(__file__).resolve().parents[1]
            if engine.dialect.name != "sqlite" or Path(engine.url.database or "").resolve() != root / "pharmaone_development.db":
                raise ValueError("Local scheduler requires the project development SQLite database")
        initialize_schema()
        with SessionLocal() as db:
            print(run_scheduled(db, policy, settings().tinyfish_api_key,
                                os.getenv("PHARMAONE_SCHEDULE_PERIOD", "")))
    except Exception:
        parser.exit(1, "Scheduled ingestion failed; check configuration and sanitized ingestion run status.\n")


if __name__ == "__main__":
    main()
