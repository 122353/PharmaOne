"""Shared validated inventory import pipeline for CSV and reference connectors."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import InventoryImport, InventoryItem, Pharmacy


def import_rows(db: Session, pharmacy: Pharmacy, rows: list[dict], errors: list[dict], source: str) -> dict:
    inserted = duplicates = 0
    seen = set()
    for row in rows:
        identity = (row["medicine_name"], row["manufacturer"], row["batch_number"])
        if identity in seen:
            duplicates += 1
            continue
        seen.add(identity)
        duplicate = db.scalar(select(InventoryItem).where(
            InventoryItem.pharmacy_id == pharmacy.id,
            InventoryItem.medicine_name == row["medicine_name"],
            InventoryItem.manufacturer == row["manufacturer"],
            InventoryItem.batch_number == row["batch_number"]))
        if duplicate:
            duplicates += 1
            continue
        db.add(InventoryItem(pharmacy_id=pharmacy.id, **row))
        inserted += 1
    db.add(InventoryImport(pharmacy_id=pharmacy.id, source=source, imported=inserted,
                           duplicates=duplicates, rejected=len(errors)))
    db.commit()
    return {"imported": inserted, "duplicates": duplicates, "rejected": len(errors),
            "incomplete": sum(row["quality_state"] == "needs_verification" for row in rows), "errors": errors}
