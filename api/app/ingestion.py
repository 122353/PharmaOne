"""Deduplicate public source records while preserving observed revisions."""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Alert, AlertVersion


def store_records(db: Session, records: list[dict], run_id: str) -> int:
    inserted = 0
    for record in records:
        alert_id = record["fingerprint"]
        existing = db.get(Alert, alert_id)
        observed = datetime.now(timezone.utc)
        if existing is None:
            existing = Alert(**record, run_id=run_id, retrieved_at=observed)
            db.add(existing)
            inserted += 1
        else:
            for key in ("product_name", "manufacturer", "batch_number", "quality_issue", "reporting_source", "raw_record"):
                setattr(existing, key, record[key])
            existing.retrieved_at = observed
            existing.run_id = run_id
        content_hash = hashlib.sha256(json.dumps(record["raw_record"], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        previous = db.scalar(select(AlertVersion).where(AlertVersion.alert_id == alert_id, AlertVersion.content_hash == content_hash))
        if previous is None:
            db.add(AlertVersion(alert_id=alert_id, content_hash=content_hash, quality_issue=record["quality_issue"], raw_record=record["raw_record"], observed_at=observed))
    db.commit()
    return inserted
