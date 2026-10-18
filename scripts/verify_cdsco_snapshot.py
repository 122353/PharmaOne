"""Read-only comparison of one stored TinyFish run with CDSCO's public NSQ table."""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select

api_root = Path(__file__).resolve().parents[1] / "api"
sys.path.insert(0, str(api_root))
os.chdir(api_root)
from app.db import SessionLocal
from app.models import Alert

RUN_ID = "c4f6314f-8d7d-4664-854d-053384dc042d"
SOURCE_URL = "https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug"
TABLE_URL = "https://cdscoonline.gov.in/CDSCO/publicNsqDrugTable"
FIELDS = {
    "product_name": "str_product_name",
    "manufacturer": "str_manufactured_by",
    "batch_number": "str_batch_no",
    "quality_issue": "str_nsq_result",
    "reporting_period": "dt_reporting_month_year",
    "reporting_source": "str_reporting_source",
}


def comparable(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def main() -> None:
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.get(TABLE_URL)
        response.raise_for_status()
        payload = response.json()
    if isinstance(payload, str):
        payload = json.loads(payload)
    official_rows = payload.get("aaData") if isinstance(payload, dict) else None
    if not isinstance(official_rows, list):
        raise RuntimeError("Official CDSCO table did not return rows")
    by_batch: dict[str, list[dict]] = {}
    for row in official_rows:
        if isinstance(row, dict):
            by_batch.setdefault(comparable(row.get("str_batch_no")), []).append(row)

    checked_at = datetime.now(timezone.utc)
    comparisons = []
    with SessionLocal() as db:
        alerts = db.scalars(select(Alert).where(Alert.run_id == RUN_ID).order_by(Alert.batch_number)).all()
        for alert in alerts:
            candidates = by_batch.get(comparable(alert.batch_number), [])
            candidates = [row for row in candidates if comparable(row.get("dt_reporting_month_year")) == comparable(alert.reporting_period)]
            if len(candidates) != 1:
                comparisons.append({"batch": alert.batch_number, "status": "missing_or_ambiguous_official_row", "official_candidates": len(candidates)})
                continue
            official = candidates[0]
            fields = {}
            for stored_name, official_name in FIELDS.items():
                stored_value = getattr(alert, stored_name)
                official_value = official.get(official_name)
                fields[stored_name] = {"stored": stored_value, "official": official_value,
                                       "exact": stored_value == official_value,
                                       "whitespace_case_equal": comparable(stored_value) == comparable(official_value)}
            fields["source_url"] = {"stored": alert.source_url, "official": SOURCE_URL,
                                    "exact": alert.source_url == SOURCE_URL}
            fields["retrieved_at"] = {"stored": alert.retrieved_at.isoformat(),
                                      "valid": alert.retrieved_at.tzinfo is not None and alert.retrieved_at <= checked_at}
            comparisons.append({"batch": alert.batch_number,
                                "status": "match" if all(value.get("whitespace_case_equal", value.get("exact", value.get("valid"))) for value in fields.values()) else "mismatch",
                                "fields": fields})

    report = {"checked_at_utc": checked_at.isoformat(), "run_id": RUN_ID, "official_source": SOURCE_URL,
              "official_table_endpoint": TABLE_URL, "official_rows_available": len(official_rows),
              "stored_rows": len(alerts), "comparisons": comparisons,
              "lookup": "Open the official NSQ page, select AUG-2026, and search each batch number; CDSCO does not expose a stable per-row URL."}
    output = Path(__file__).resolve().parents[1] / "evidence" / "cdsco-live-compare-2026-10-18.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"stored={len(alerts)} official_table_rows={len(official_rows)} matched={sum(row['status'] == 'match' for row in comparisons)} mismatched={sum(row['status'] == 'mismatch' for row in comparisons)} missing={sum(row['status'] == 'missing_or_ambiguous_official_row' for row in comparisons)}")
    print(f"report={output}")


if __name__ == "__main__":
    main()
