"""Deduplicate public source records while preserving observed revisions."""
import hashlib
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import Alert, AlertVersion
from .tinyfish import normalize_record


def meaningful_hash(record: dict) -> str:
    """Hash regulatory meaning, ignoring page layout and whitespace changes."""
    keys = ("product_name", "manufacturer", "batch_number", "quality_issue", "reporting_period", "reporting_source", "classification")
    content = {key: " ".join(str(record.get(key) or "").split()).casefold() for key in keys}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def store_records(db: Session, records: list[dict], run_id: str, *, commit: bool = True) -> int:
    inserted = 0
    seen_in_run = set()
    for record in records:
        alert_id = record["fingerprint"]
        if alert_id in seen_in_run:
            continue
        seen_in_run.add(alert_id)
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
        content_hash = meaningful_hash(record)
        versions = db.scalars(select(AlertVersion).where(AlertVersion.alert_id == alert_id)).all()
        if versions:
            latest = max(version.observed_at for version in versions)
            if latest.tzinfo is None:
                latest = latest.replace(tzinfo=timezone.utc)
            observed = max(observed, latest + timedelta(microseconds=1))
        known = any(v.content_hash == content_hash for v in versions)
        if not known:
            for version in versions:
                try:
                    if meaningful_hash(normalize_record(version.raw_record, record["reporting_period"])) == content_hash:
                        known = True
                        break
                except (ValueError, TypeError):
                    continue
        if not known:
            db.add(AlertVersion(alert_id=alert_id, content_hash=content_hash, quality_issue=record["quality_issue"], raw_record=record["raw_record"], observed_at=observed))
    if commit:
        db.commit()
    else:
        db.flush()
    return inserted
