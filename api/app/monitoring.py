
"""Local regulatory monitoring and event detection prototype."""

import hashlib
import json

from .matching import compare


def monitor_inventory(inventory, regulatory_records, previous_events=None):
    """Compare inventory against reports and return newly detected events."""

    previous_events = set(previous_events or [])
    events = []
    seen = set()

    for item in inventory:
        for report in regulatory_records:
            status, evidence = compare(item, report)

            if status not in {"potential_match", "needs_verification"}:
                continue

            identity = {
                "medicine": item.get("medicine_name"),
                "manufacturer": item.get("manufacturer"),
                "batch": item.get("batch_number"),
                "regulatory_product": report.get("product_name"),
                "regulatory_batch": report.get("batch_number"),
                "source": report.get("source_url"),
            }

            event_id = hashlib.sha256(
                json.dumps(identity, sort_keys=True).encode()
            ).hexdigest()[:20]

            if event_id in previous_events or event_id in seen:
                continue

            seen.add(event_id)

            events.append({
                "event_id": event_id,
                "status": status,
                "medicine": item.get("medicine_name"),
                "batch": item.get("batch_number"),
                "regulatory_medicine": report.get("product_name"),
                "quality_issue": report.get("quality_issue"),
                "source_url": report.get("source_url"),
                "match_evidence": evidence,
                "requires_pharmacist_review": True,
            })

    return events
