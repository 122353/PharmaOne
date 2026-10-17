"""Explicit service-key CDSCO sync for an operator-controlled scheduler.

Run only when the team has budgeted TinyFish usage: python -m app.ingest_service AUG-2026
"""
import argparse
from datetime import datetime, timezone
from sqlalchemy import select
from .config import settings
from .db import Base, engine, SessionLocal
from .models import Alert, Pharmacy, IngestionRun
from .tinyfish import retrieve
from .ingestion import store_records
from .main import rerun


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("period", help="CDSCO reporting period, e.g. AUG-2026")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    key = settings().tinyfish_service_key
    if not key:
        parser.error("TINYFISH_SERVICE_KEY is required; no user key will be substituted")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        run = IngestionRun(period=args.period)
        db.add(run)
        db.commit()
        try:
            records, provider_run = retrieve(key, args.period, args.limit)
            store_records(db, records, run.id)
            run.status = "succeeded"
            run.provider_run_id = provider_run
            run.record_count = len(records)
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            for pharmacy in db.scalars(select(Pharmacy)):
                rerun(db, pharmacy)
            print(f"Run {run.id}: stored {len(records)} source records")
        except Exception:
            run.status = "failed"
            run.error = "Provider or source retrieval failed"
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            raise


if __name__ == "__main__":
    main()
