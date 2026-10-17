"""Import a TinyFish connector run only after independent CDSCO field verification."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal, initialize_schema
from .ingestion import store_records
from .main import rerun
from .models import IngestionRun, Pharmacy
from .tinyfish import SOURCE_URL, normalize_record


ROOT = Path(__file__).resolve().parents[2]


def import_verified_snapshot(db: Session, snapshot_path: Path, report_path: Path) -> int:
    raw = snapshot_path.read_bytes()
    snapshot = json.loads(raw)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    records = snapshot.get("records")
    if (
        report.get("status") != "verified"
        or report.get("mismatches") != []
        or report.get("snapshot_sha256") != hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
        or snapshot.get("source_url") != SOURCE_URL
        or report.get("source_url") != SOURCE_URL
        or snapshot.get("provider_run_id") != report.get("provider_run_id")
        or not isinstance(records, list)
        or not 1 <= len(records) <= 25
        or report.get("records_checked") != len(records)
        or report.get("fields_checked") != len(records) * 6
    ):
        raise ValueError("Snapshot does not match successful source verification")
    provider_id = snapshot["provider_run_id"]
    if db.scalar(select(IngestionRun).where(IngestionRun.provider_run_id == provider_id)):
        return 0
    normalized = [normalize_record(record, snapshot["reporting_period"]) for record in records]
    run = IngestionRun(period=snapshot["reporting_period"], provider_run_id=provider_id)
    db.add(run)
    db.commit()
    store_records(db, normalized, run.id)
    run.status = "succeeded"
    run.record_count = len(normalized)
    run.finished_at = datetime.now(timezone.utc)
    db.commit()
    for pharmacy in db.scalars(select(Pharmacy)):
        rerun(db, pharmacy)
    return len(normalized)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "evidence/cdsco-aug-2026-tinyfish.json")
    parser.add_argument("--report", type=Path, default=ROOT / "evidence/cdsco-verification-report.json")
    args = parser.parse_args()
    initialize_schema()
    with SessionLocal() as db:
        count = import_verified_snapshot(db, args.snapshot, args.report)
    print(f"Verified TinyFish snapshot: {count} records imported (0 means already imported)")


if __name__ == "__main__":
    main()
