"""Persistent pharmacy notifications with revision-aware deduplication."""

import hashlib
import json
import unicodedata

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    Alert,
    InventoryItem,
    Match,
    MonitoringNotification,
    Pharmacy,
)


def _event_id(pharmacy: Pharmacy, item: InventoryItem, alert: Alert) -> str:
    """Identify one regulatory finding against one version of stock identity."""
    event = {
        "pharmacy_id": pharmacy.id,
        "inventory_id": item.id,
        "medicine_name": " ".join(unicodedata.normalize("NFKC", item.medicine_name or "").casefold().split()),
        "manufacturer": " ".join(unicodedata.normalize("NFKC", item.manufacturer or "").casefold().split()),
        "batch_number": " ".join(unicodedata.normalize("NFKC", item.batch_number or "").casefold().split()),
        "strength": " ".join(unicodedata.normalize("NFKC", item.strength or "").casefold().split()),
        "alert_id": alert.fingerprint,
        "alert_product": alert.product_name,
        "alert_manufacturer": alert.manufacturer,
        "alert_batch": alert.batch_number,
        "reporting_period": alert.reporting_period,
        "reporting_source": alert.reporting_source,
        "quality_issue": " ".join((alert.quality_issue or "").split()),
    }
    payload = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _legacy_event_id(pharmacy: Pharmacy, item: InventoryItem, alert: Alert) -> str:
    return hashlib.sha256(
        f"{pharmacy.id}:{item.id}:{alert.fingerprint}".encode()
    ).hexdigest()


def sync_notifications(db: Session, pharmacy: Pharmacy) -> dict:
    """Create current events and deactivate notices whose evidence changed.

    The caller controls commit/rollback. Read state survives repeated syncs and
    event supersession. A database uniqueness constraint handles concurrent
    callers in addition to the pre-insert lookup.
    """
    rows = db.execute(
        select(Match, InventoryItem, Alert)
        .join(InventoryItem, InventoryItem.id == Match.inventory_id)
        .join(Alert, Alert.fingerprint == Match.alert_id)
        .where(
            Match.pharmacy_id == pharmacy.id,
            Match.status.in_(("potential_match", "needs_verification")),
            InventoryItem.pharmacy_id == pharmacy.id,
        )
    ).all()

    existing_notifications = db.scalars(
        select(MonitoringNotification).where(
            MonitoringNotification.pharmacy_id == pharmacy.id
        )
    ).all()
    by_event = {notification.event_id: notification for notification in existing_notifications}
    current_event_ids: set[str] = set()
    created = 0
    skipped = 0
    reactivated = 0

    for match, item, alert in rows:
        event_id = _event_id(pharmacy, item, alert)
        current_event_ids.add(event_id)
        notification = by_event.get(event_id)

        # Upgrade notifications created before stock/source revisions became
        # part of the deduplication key, preserving their acknowledged state.
        if notification is None:
            legacy_id = _legacy_event_id(pharmacy, item, alert)
            notification = by_event.get(legacy_id)
            if notification is not None:
                by_event.pop(legacy_id, None)
                notification.event_id = event_id
                by_event[event_id] = notification

        title = (
            "Potential regulatory match"
            if match.status == "potential_match"
            else "Regulatory verification required"
        )
        message = (
            f"{item.medicine_name} | Batch {item.batch_number or 'missing'}. "
            f"CDSCO finding: {alert.quality_issue or 'See official source'}. "
            "Pharmacist verification required."
        )

        if notification is not None:
            if not notification.is_active:
                reactivated += 1
            notification.is_active = True
            notification.status = match.status
            notification.title = title
            notification.message = message
            skipped += 1
            continue

        notification = MonitoringNotification(
            pharmacy_id=pharmacy.id,
            event_id=event_id,
            inventory_id=item.id,
            alert_id=alert.fingerprint,
            status=match.status,
            title=title,
            message=message,
            is_read=False,
            is_active=True,
        )
        try:
            with db.begin_nested():
                db.add(notification)
                db.flush()
            by_event[event_id] = notification
            created += 1
        except IntegrityError:
            # A concurrent recheck created the same event. Keep the transaction
            # usable and count it as deduplicated.
            skipped += 1

    stale = 0
    for notification in existing_notifications:
        if notification.is_active and notification.event_id not in current_event_ids:
            notification.is_active = False
            stale += 1

    db.flush()
    return {
        "created": created,
        "skipped": skipped,
        "reactivated": reactivated,
        "deactivated": stale,
        "total_matches": len(rows),
    }
