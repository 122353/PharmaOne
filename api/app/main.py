from datetime import date, datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session
from .auth import current_user
from .config import settings
from .db import get_db, initialize_schema
from .models import Pharmacy, InventoryItem, Alert, AlertVersion, Match, Investigation, AuditEvent, IngestionRun, InventoryImport
from .ingestion import store_records
from .csv_import import parse_csv
from .inventory_service import import_rows
from .matching import compare
from .ml import pharma_classify
from .tinyfish import SOURCE_URL
from .contextos import router as contextos_router
from .scan import router as scan_router
from .suppliers import router as suppliers_router
from .evidence import router as evidence_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_schema()
    yield


app = FastAPI(title="PharmaOne API", version="0.1.0", lifespan=lifespan)
app.include_router(contextos_router)
app.include_router(scan_router)
app.include_router(suppliers_router)
app.include_router(evidence_router)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings().allowed_origins.split(",")], allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])


def fields(obj, names):
    return {name: getattr(obj, name) for name in names}


def pharmacy_for(db: Session, user: str) -> Pharmacy:
    pharmacy = db.scalar(select(Pharmacy).where(Pharmacy.owner_id == user))
    if not pharmacy:
        raise HTTPException(404, "Create your pharmacy profile first")
    return pharmacy


def alert_out(alert: Alert):
    return {**fields(alert, ["fingerprint", "product_name", "manufacturer", "batch_number", "quality_issue", "reporting_period", "reporting_source", "source_url", "retrieved_at", "classification"]),
            "pharma_classify": pharma_classify(alert.quality_issue)}


def item_out(item: InventoryItem):
    return fields(item, ["id", "medicine_name", "manufacturer", "batch_number", "strength", "expiry_date", "quantity", "quality_state", "created_at"])


def match_out(match: Match, db: Session):
    return {**fields(match, ["id", "status", "explanation", "checked_at"]), "inventory": item_out(db.get(InventoryItem, match.inventory_id)), "alert": alert_out(db.get(Alert, match.alert_id))}


def rerun(db: Session, pharmacy: Pharmacy, *, commit: bool = True):
    existing = {(m.inventory_id, m.alert_id): m for m in db.scalars(select(Match).where(Match.pharmacy_id == pharmacy.id))}
    seen = set()
    alerts = db.scalars(select(Alert)).all()
    items = db.scalars(select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy.id)).all()
    for item in items:
        for alert in alerts:
            status, explanation = compare(item_out(item), alert_out(alert))
            if status != "no_identified_match":
                pair = (item.id, alert.fingerprint)
                seen.add(pair)
                match = existing.get(pair) or Match(pharmacy_id=pharmacy.id, inventory_id=item.id, alert_id=alert.fingerprint)
                match.status, match.explanation, match.checked_at = status, explanation, datetime.now(timezone.utc)
                db.add(match)
    for pair, match in existing.items():
        if pair not in seen:
            if db.scalar(select(Investigation).where(Investigation.match_id == match.id)):
                match.status = "no_identified_match"
                match.explanation = {**match.explanation, "note": "Identifiers changed since this investigation was recorded."}
            else:
                db.delete(match)
    if commit:
        db.commit()
    else:
        db.flush()


class PharmacyInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    contact_name: str = Field(default="", max_length=160)
    kind: str = Field(default="retail", pattern="^(retail|hospital|distributor|other)$")
    city: str = Field(default="", max_length=100)
    state: str = Field(default="", max_length=100)
    inventory_format: str = Field(default="csv", pattern="^(csv|excel|erp|manual)$")
    batch_available: bool = True
    manufacturer_available: bool = True


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/me")
def me(user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = db.scalar(select(Pharmacy).where(Pharmacy.owner_id == user))
    return {"user_id": user, "pharmacy": fields(pharmacy, ["id", "name", "contact_name", "kind", "city", "state", "inventory_format", "batch_available", "manufacturer_available"]) if pharmacy else None}


@app.get("/api/pharmacies/current")
def current_pharmacy(user: str = Depends(current_user), db: Session = Depends(get_db)):
    return me(user, db)["pharmacy"]


@app.put("/api/pharmacies/current")
def save_pharmacy(data: PharmacyInput, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = db.scalar(select(Pharmacy).where(Pharmacy.owner_id == user)) or Pharmacy(owner_id=user)
    for key, value in data.model_dump().items():
        setattr(pharmacy, key, value)
    db.add(pharmacy)
    db.commit()
    return current_pharmacy(user, db)


@app.post("/api/inventory/import")
async def import_inventory(file: UploadFile = File(...), user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a CSV file")
    raw = await file.read(2 * 1024 * 1024 + 1)
    try:
        rows, errors = parse_csv(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    result = import_rows(db, pharmacy, rows, errors, "csv")
    rerun(db, pharmacy)
    return result


@app.post("/api/inventory/connectors/mock/import")
def import_reference_erp(user: str = Depends(current_user), db: Session = Depends(get_db)):
    """Explicitly synthetic local reference adapter; no commercial ERP connection."""
    pharmacy = pharmacy_for(db, user)
    sample = b"medicine_name,manufacturer,batch_number,strength,expiry_date,quantity\nSynthetic ERP Medicine,Example Manufacturer,SYN-DEMO-001,10mg,2028-01-01,3\n"
    rows, errors = parse_csv(sample)
    result = import_rows(db, pharmacy, rows, errors, "synthetic_mock_erp")
    rerun(db, pharmacy)
    return {**result, "synthetic": True}


@app.get("/api/inventory/imports")
def inventory_imports(user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    return [fields(record, ["id", "source", "imported", "duplicates", "rejected", "created_at"])
            for record in db.scalars(select(InventoryImport).where(InventoryImport.pharmacy_id == pharmacy.id)
                                     .order_by(desc(InventoryImport.created_at)).limit(50))]


@app.get("/api/inventory")
def inventory(q: str = "", user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    stmt = select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy.id).order_by(desc(InventoryItem.created_at)).limit(500)
    if q:
        stmt = stmt.where(InventoryItem.medicine_name.ilike(f"%{q[:100]}%"))
    return [item_out(item) for item in db.scalars(stmt)]


class InventoryEdit(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=255)
    manufacturer: str = Field(default="", max_length=255)
    batch_number: str = Field(default="", max_length=100)
    strength: str = Field(default="", max_length=100)
    expiry_date: str = Field(default="", max_length=30)
    quantity: int = Field(ge=0, le=10_000_000)

    @field_validator("expiry_date")
    @classmethod
    def valid_expiry(cls, value: str) -> str:
        if value:
            date.fromisoformat(value)
        return value


@app.patch("/api/inventory/{item_id}")
def edit_inventory(item_id: str, data: InventoryEdit, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    item = db.scalar(select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.pharmacy_id == pharmacy.id))
    if not item:
        raise HTTPException(404, "Inventory item not found")
    duplicate = db.scalar(select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy.id, InventoryItem.id != item_id, InventoryItem.medicine_name == data.medicine_name, InventoryItem.manufacturer == data.manufacturer, InventoryItem.batch_number == data.batch_number))
    if duplicate:
        raise HTTPException(409, "An inventory item with these identifiers already exists")
    old = item_out(item)
    for key, value in data.model_dump().items():
        setattr(item, key, value)
    item.quality_state = "ready" if item.manufacturer and item.batch_number else "needs_verification"
    db.add(AuditEvent(pharmacy_id=pharmacy.id, actor_id=user, action="inventory_edited", entity_id=item.id, detail=jsonable_encoder({"before": old, "after": data.model_dump()})))
    db.commit()
    rerun(db, pharmacy)
    return item_out(item)


@app.get("/api/alerts")
def alerts(q: str = "", period: str = "", user: str = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Alert).order_by(desc(Alert.retrieved_at)).limit(200)
    if q:
        stmt = stmt.where(Alert.product_name.ilike(f"%{q[:100]}%"))
    if period:
        stmt = stmt.where(Alert.reporting_period == period)
    return [alert_out(a) for a in db.scalars(stmt)]


@app.get("/api/alerts/{alert_id}")
def alert_detail(alert_id: str, user: str = Depends(current_user), db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alert not found")
    return alert_out(alert)


@app.get("/api/alerts/{alert_id}/versions")
def alert_versions(alert_id: str, user: str = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Alert, alert_id) is None:
        raise HTTPException(404, "Alert not found")
    return [fields(v, ["id", "quality_issue", "observed_at"]) for v in db.scalars(select(AlertVersion).where(AlertVersion.alert_id == alert_id).order_by(AlertVersion.observed_at))]


@app.get("/api/regulatory/changes")
def regulatory_changes(user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    affected = set(db.scalars(select(Match.alert_id).where(Match.pharmacy_id == pharmacy.id,
                                                      Match.status != "no_identified_match")))
    changes = []
    for version in db.scalars(select(AlertVersion).order_by(desc(AlertVersion.observed_at)).limit(100)):
        alert = db.get(Alert, version.alert_id)
        if not alert:
            continue
        first = db.scalar(select(AlertVersion.id).where(AlertVersion.alert_id == version.alert_id)
                          .order_by(AlertVersion.observed_at, AlertVersion.id).limit(1))
        changes.append({"id": version.id, "kind": "added" if first == version.id else "updated",
                        "alert_id": alert.fingerprint, "product_name": alert.product_name,
                        "batch_number": alert.batch_number, "quality_issue": version.quality_issue,
                        "source_url": alert.source_url, "observed_at": version.observed_at,
                        "own_inventory_impact": alert.fingerprint in affected})
    return changes


@app.get("/api/matches")
def matches(user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    return [match_out(m, db) for m in db.scalars(select(Match).where(Match.pharmacy_id == pharmacy.id).limit(500))]


@app.post("/api/matches/recheck")
def recheck(user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    rerun(db, pharmacy)
    return {"matches": db.scalar(select(func.count()).select_from(Match).where(Match.pharmacy_id == pharmacy.id))}


@app.get("/api/investigations")
def investigations(user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    return [investigation_out(i, db) for i in db.scalars(select(Investigation).where(Investigation.pharmacy_id == pharmacy.id).order_by(desc(Investigation.updated_at)))]


REVIEW_STATUSES = {"open", "under_investigation", "reviewed", "closed"}
DECISION_ACTIONS = {"investigation_" + value for value in REVIEW_STATUSES | {"physical_verification_pending", "simulated_hold"}}


def investigation_out(record: Investigation, db: Session):
    events = db.scalars(select(AuditEvent).where(AuditEvent.pharmacy_id == record.pharmacy_id,
                       AuditEvent.entity_id == record.id, AuditEvent.action.in_(DECISION_ACTIONS))
                       .order_by(AuditEvent.created_at, AuditEvent.id)).all()
    latest = events[-1] if events else None
    detail = latest.detail if latest and isinstance(latest.detail, dict) else {}
    review_status = record.status if record.status in REVIEW_STATUSES else next(
        (event.action.removeprefix("investigation_") for event in reversed(events)
         if event.action.removeprefix("investigation_") in REVIEW_STATUSES), "under_investigation")
    physical_verified = bool(detail.get("physical_verified"))
    physical_status = detail.get("physical_status") if detail.get("physical_status") in {"verified", "pending", "not_recorded"} else (
        "verified" if physical_verified else "pending" if any(
            event.action == "investigation_physical_verification_pending" for event in events) else "not_recorded")
    return {**fields(record, ["id", "match_id", "note", "updated_at"]),
            "status": review_status, "physical_status": physical_status,
            "simulated_hold": any(event.action == "investigation_simulated_hold" for event in events),
            "record_reviewed": bool(detail.get("record_reviewed")), "physical_verified": physical_verified}


class InvestigationInput(BaseModel):
    match_id: str
    status: str = Field(pattern="^(open|under_investigation|physical_verification_pending|reviewed|closed|simulated_hold)$")
    note: str = Field(default="", max_length=2000)
    record_reviewed: bool = False
    physical_verified: bool = False


@app.post("/api/investigations")
def save_investigation(data: InvestigationInput, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    match = db.scalar(select(Match).where(Match.id == data.match_id, Match.pharmacy_id == pharmacy.id))
    if not match:
        raise HTTPException(404, "Match not found")
    existing = db.scalar(select(Investigation).where(Investigation.match_id == match.id, Investigation.pharmacy_id == pharmacy.id))
    record = existing or Investigation(pharmacy_id=pharmacy.id, match_id=match.id)
    previous = investigation_out(existing, db) if existing else None
    review_status = data.status if data.status in REVIEW_STATUSES else (previous["status"] if previous else "under_investigation")
    note = data.note if data.note.strip() or not previous else previous["note"]
    physical_verified = data.physical_verified and data.status != "physical_verification_pending"
    physical_status = ("pending" if data.status == "physical_verification_pending" else
                       "verified" if physical_verified else
                       "pending" if previous and previous["physical_status"] != "not_recorded" else "not_recorded")
    hold = data.status == "simulated_hold" or bool(previous and previous["simulated_hold"])
    if previous and (review_status, note, data.record_reviewed, physical_verified, physical_status, hold) == (
        previous["status"], previous["note"], previous["record_reviewed"], previous["physical_verified"],
        previous["physical_status"], previous["simulated_hold"]):
        return previous
    record.status, record.note = review_status, note
    db.add(record)
    db.flush()
    db.add(AuditEvent(pharmacy_id=pharmacy.id, actor_id=user, action="investigation_" + data.status,
                      entity_id=record.id, detail={"note": note, "record_reviewed": data.record_reviewed,
                                                   "physical_verified": physical_verified,
                                                   "physical_status": physical_status, "simulated_hold": hold,
                                                   "review_status": review_status}))
    db.commit()
    return investigation_out(record, db)


@app.get("/api/investigations/{record_id}/events")
def investigation_events(record_id: str, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    record = db.scalar(select(Investigation).where(Investigation.id == record_id, Investigation.pharmacy_id == pharmacy.id))
    if not record:
        raise HTTPException(404, "Investigation not found")
    return [fields(e, ["id", "actor_id", "action", "detail", "created_at"]) for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_id == record.id, AuditEvent.pharmacy_id == pharmacy.id).order_by(AuditEvent.created_at))]


@app.get("/api/ingestion/status")
def ingestion_status(user: str = Depends(current_user), db: Session = Depends(get_db)):
    latest = db.scalar(select(IngestionRun).where(IngestionRun.requesting_user_id.is_(None)).order_by(desc(IngestionRun.started_at)).limit(1))
    success = db.scalar(select(IngestionRun).where(IngestionRun.requesting_user_id.is_(None), IngestionRun.status == "succeeded").order_by(desc(IngestionRun.finished_at)).limit(1))
    return {"state": latest.status if latest else "never_synced", "last_checked": success.finished_at if success else None, "record_count": success.record_count if success else 0, "source_url": SOURCE_URL, "error": latest.error if latest else ""}


@app.get("/api/dashboard")
def dashboard(user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    items = db.scalars(select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy.id)).all()
    own_matches = db.scalars(select(Match).where(Match.pharmacy_id == pharmacy.id, Match.status != "no_identified_match")).all()
    open_count = db.scalar(select(func.count()).select_from(Investigation).where(Investigation.pharmacy_id == pharmacy.id, Investigation.status == "open"))
    questions = []
    if any(not x.batch_number for x in items):
        questions.append("Some inventory rows lack batch numbers. Please confirm them before deciding whether an alert applies.")
    if any(not x.manufacturer for x in items):
        questions.append("Some inventory rows lack a manufacturer. Add it to improve verification.")
    if not items:
        questions.append("Import your batch-wise CSV to begin checking available official records.")
    return {"pharmacy": pharmacy.name, "inventory_count": len(items), "potential_count": sum(m.status == "potential_match" for m in own_matches), "verification_count": sum(m.status == "needs_verification" for m in own_matches) + sum(i.quality_state == "needs_verification" for i in items), "open_investigations": open_count, "review_queue": [match_out(m, db) for m in own_matches[:3]], "recent_alerts": [alert_out(a) for a in db.scalars(select(Alert).order_by(desc(Alert.retrieved_at)).limit(5))], "clarifications": questions[:3], "source": ingestion_status(user, db)}
