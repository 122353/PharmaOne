"""Import a TinyFish connector run only after independent CDSCO field verification."""
import argparse
import hashlib
import json
import re
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
    provider_run_url = (
        f"https://agent.tinyfish.ai/runs/{provider_id}"
        if re.fullmatch(r"[0-9a-fA-F-]{36}", str(provider_id))
        else ""
    )
    retrieval_metadata = {
        "reporting_period": snapshot["reporting_period"],
        "source_url": SOURCE_URL,
        "verified_at": report.get("verified_at"),
        "snapshot_sha256": report["snapshot_sha256"],
        "record_count": len(records),
        "imported_as_historical": True,
    }
    existing_run = db.scalar(select(IngestionRun).where(IngestionRun.provider_run_id == provider_id))
    if existing_run:
        # Older local snapshot imports predate source_kind provenance. Repair
        # only the exact verified historical run; never relabel a live run.
        if (
            existing_run.source_kind == "unknown"
            and existing_run.status == "succeeded"
            and existing_run.period == snapshot["reporting_period"]
        ):
            existing_run.source_kind = "historical_snapshot"
            existing_run.provider_run_url = provider_run_url
            existing_run.retrieval_metadata = retrieval_metadata
            db.commit()
        return 0
    normalized = [normalize_record(record, snapshot["reporting_period"]) for record in records]
    run = IngestionRun(
        period=snapshot["reporting_period"],
        provider_run_id=provider_id,
        provider_run_url=provider_run_url,
        source_kind="historical_snapshot",
        retrieval_metadata=retrieval_metadata,
    )
    db.add(run)
    db.flush()
    store_records(db, normalized, run.id, commit=False)
    run.status = "succeeded"
    run.record_count = len(normalized)
    run.finished_at = datetime.now(timezone.utc)
    for pharmacy in db.scalars(select(Pharmacy)):
        rerun(db, pharmacy, commit=False)
    db.commit()
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
