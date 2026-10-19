"""Operator-only CDSCO synchronization using one backend TinyFish key.

Usage (explicit paid operation): python -m app.ingest_service AUG-2026 --limit 10
"""
import argparse
import re
import time
from pathlib import Path
from threading import Lock
from contextlib import contextmanager
from datetime import datetime, timezone

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal, engine, initialize_schema
from .ingestion import store_records
from .main import rerun
from .models import IngestionRun, Pharmacy
from .tinyfish import SOURCE_URL, retrieve


_memory_lock = Lock()


@contextmanager
def operator_lock(target_engine=engine):
    """Hold a PostgreSQL advisory lock on one connection for the whole run."""
    if target_engine.dialect.name == "sqlite":
        database = target_engine.url.database
        if not database or database == ":memory:":
            if not _memory_lock.acquire(blocking=False):
                raise RuntimeError("Another regulatory synchronization is running")
            try:
                yield
            finally:
                _memory_lock.release()
            return
        path = Path(database).resolve().with_suffix(".db.sync.lock")
        with path.open("a+b") as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                import os
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise RuntimeError("Another regulatory synchronization is running") from None
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if target_engine.dialect.name != "postgresql":
        raise RuntimeError("Unsupported synchronization database")
    with target_engine.connect() as connection:
        acquired = connection.scalar(text("select pg_try_advisory_lock(730114223)"))
        connection.commit()
        if not acquired:
            raise RuntimeError("Another regulatory synchronization is running")
        try:
            yield
        finally:
            connection.execute(text("select pg_advisory_unlock(730114223)"))
            connection.commit()


def sync_once(db: Session, key: str, period: str, limit: int = 10, *, provider=retrieve,
              max_requests: int = 1, source_kind: str = "operator_live",
              method: str = "operator_tinyfish", started_at: datetime | None = None) -> IngestionRun:
    if not key:
        raise RuntimeError("TINYFISH_API_KEY is not configured")
    if period != "LATEST" and not re.fullmatch(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-20\d\d", period):
        raise ValueError("Period must be MON-YYYY or LATEST")
    if not 1 <= limit <= 25:
        raise ValueError("Limit must be 1 to 25")
    if max_requests not in (1, 2):
        raise ValueError("Request budget must be 1 or 2")
    if source_kind not in {"operator_live", "historical_snapshot"}:
        raise ValueError("Unsupported source provenance")
    if source_kind == "historical_snapshot" and provider is retrieve:
        raise ValueError("Historical playback requires an offline provider")
    run = IngestionRun(
        period=period,
        requesting_user_id=None,
        connection_id=None,
        source_kind=source_kind,
        started_at=started_at or datetime.now(timezone.utc),
        retrieval_metadata={
            "method": method,
            "source_url": SOURCE_URL,
            "reporting_period": period,
            "requested_limit": limit,
            "max_provider_requests": max_requests,
            "provider_requests": 0,
            "imported_as_historical": source_kind == "historical_snapshot",
        },
    )
    db.add(run)
    db.commit()
    run_id = run.id
    try:
        for attempt in range(max_requests):
            try:
                run.retrieval_metadata = {**run.retrieval_metadata, "provider_requests": attempt + 1}
                db.commit()
                records, provider_run = provider(key, period, limit)
                if not records:
                    raise RuntimeError("TinyFish returned no source records")
                if not isinstance(records, list) or len(records) > limit:
                    raise ValueError("Provider exceeded record limit")
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 or attempt + 1 >= max_requests:
                    raise
                time.sleep(1)
        store_records(db, records, run_id, commit=False)
        for pharmacy in db.scalars(select(Pharmacy)).all():
            rerun(db, pharmacy, commit=False)
        run.status = "succeeded"
        run.provider_run_id = provider_run
        if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", provider_run or ""):
            run.provider_run_url = f"https://agent.tinyfish.ai/runs/{provider_run}"
        run.record_count = len(records)
        run.finished_at = datetime.now(timezone.utc)
        run.retrieval_metadata = {
            **run.retrieval_metadata,
            ("retrieved_at" if source_kind == "operator_live" else "imported_at"): run.finished_at.isoformat(),
            "provider_run_id": provider_run,
        }
        db.commit()
        return run
    except Exception:
        db.rollback()
        failed = db.get(IngestionRun, run_id)
        failed.status = "failed"
        failed.error = "Provider or source retrieval failed"
        failed.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("period", help="CDSCO reporting period, e.g. AUG-2026, or LATEST")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--max-requests", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    if not settings().tinyfish_api_key:
        parser.error("TINYFISH_API_KEY is required")
    initialize_schema()
    with operator_lock(), SessionLocal() as db:
        try:
            run = sync_once(db, settings().tinyfish_api_key, args.period, args.limit, max_requests=args.max_requests)
        except Exception:
            parser.exit(1, "Regulatory synchronization failed; details are recorded without credentials.\n")
        print(f"Run {run.id}: stored {run.record_count} source records")


if __name__ == "__main__":
    main()
