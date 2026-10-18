"""Operator-only CDSCO synchronization using one backend TinyFish key.

Usage (explicit paid operation): python -m app.ingest_service AUG-2026 --limit 10
"""
import argparse
import re
import time
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
from .tinyfish import retrieve


@contextmanager
def operator_lock():
    """Hold a PostgreSQL advisory lock on one connection for the whole run."""
    if engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as connection:
        acquired = connection.scalar(text("select pg_try_advisory_lock(730114223)"))
        connection.commit()
        if not acquired:
            raise RuntimeError("Another regulatory synchronization is running")
        try:
            yield
        finally:
            connection.execute(text("select pg_advisory_unlock(730114223)"))
            connection.commit()


def sync_once(db: Session, key: str, period: str, limit: int = 10, *, provider=retrieve) -> IngestionRun:
    if not key:
        raise RuntimeError("TINYFISH_API_KEY is not configured")
    if not re.fullmatch(r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-20\d\d", period):
        raise ValueError("Period must be MON-YYYY")
    if not 1 <= limit <= 25:
        raise ValueError("Limit must be 1 to 25")
    run = IngestionRun(period=period, requesting_user_id=None, connection_id=None)
    db.add(run)
    db.commit()
    run_id = run.id
    try:
        for attempt in range(2):
            try:
                records, provider_run = provider(key, period, limit)
                if not records:
                    raise RuntimeError("TinyFish returned no source records")
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 or attempt:
                    raise
                time.sleep(1)
        store_records(db, records, run_id, commit=False)
        for pharmacy in db.scalars(select(Pharmacy)).all():
            rerun(db, pharmacy, commit=False)
        run.status = "succeeded"
        run.provider_run_id = provider_run
        run.record_count = len(records)
        run.finished_at = datetime.now(timezone.utc)
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
    parser.add_argument("period", help="CDSCO reporting period, e.g. AUG-2026")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not settings().tinyfish_api_key:
        parser.error("TINYFISH_API_KEY is required")
    initialize_schema()
    with operator_lock(), SessionLocal() as db:
        try:
            run = sync_once(db, settings().tinyfish_api_key, args.period, args.limit)
        except Exception:
            parser.exit(1, "Regulatory synchronization failed; details are recorded without credentials.\n")
        print(f"Run {run.id}: stored {run.record_count} source records")


if __name__ == "__main__":
    main()
