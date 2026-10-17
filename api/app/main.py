from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.orm import Session
from .auth import current_user
from .config import settings
from .db import Base, engine, get_db
from .models import Pharmacy, InventoryItem, Alert, AlertVersion, Match, Investigation, AuditEvent, TinyfishConnection, IngestionRun
from .ingestion import store_records
from .csv_import import parse_csv
from .matching import compare
from .tinyfish import retrieve, SOURCE_URL
from .crypto import encrypt, decrypt, fingerprint as key_fingerprint

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="PharmaOne API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings().allowed_origins.split(",")], allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])


def fields(obj, names):
    return {name: getattr(obj, name) for name in names}


def pharmacy_for(db: Session, user: str) -> Pharmacy:
    pharmacy = db.scalar(select(Pharmacy).where(Pharmacy.owner_id == user))
    if not pharmacy:
        raise HTTPException(404, "Create your pharmacy profile first")
    return pharmacy


def alert_out(alert: Alert):
    return fields(alert, ["fingerprint", "product_name", "manufacturer", "batch_number", "quality_issue", "reporting_period", "reporting_source", "source_url", "retrieved_at", "classification"])


def item_out(item: InventoryItem):
    return fields(item, ["id", "medicine_name", "manufacturer", "batch_number", "strength", "expiry_date", "quantity", "quality_state", "created_at"])


def match_out(match: Match, db: Session):
    return {**fields(match, ["id", "status", "explanation", "checked_at"]), "inventory": item_out(db.get(InventoryItem, match.inventory_id)), "alert": alert_out(db.get(Alert, match.alert_id))}


def rerun(db: Session, pharmacy: Pharmacy):
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
    db.commit()


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
    inserted = duplicates = 0
    for row in rows:
        duplicate = db.scalar(select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy.id, InventoryItem.medicine_name == row["medicine_name"], InventoryItem.manufacturer == row["manufacturer"], InventoryItem.batch_number == row["batch_number"]))
        if duplicate:
            duplicates += 1
            continue
        db.add(InventoryItem(pharmacy_id=pharmacy.id, **row))
        inserted += 1
    db.commit()
    rerun(db, pharmacy)
    return {"imported": inserted, "duplicates": duplicates, "rejected": len(errors), "incomplete": sum(r["quality_state"] == "needs_verification" for r in rows), "errors": errors}


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
    return [fields(i, ["id", "match_id", "status", "note", "updated_at"]) for i in db.scalars(select(Investigation).where(Investigation.pharmacy_id == pharmacy.id).order_by(desc(Investigation.updated_at)))]


class InvestigationInput(BaseModel):
    match_id: str
    status: str = Field(pattern="^(open|reviewed|simulated_hold)$")
    note: str = Field(default="", max_length=2000)


@app.post("/api/investigations")
def save_investigation(data: InvestigationInput, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    match = db.scalar(select(Match).where(Match.id == data.match_id, Match.pharmacy_id == pharmacy.id))
    if not match:
        raise HTTPException(404, "Match not found")
    record = db.scalar(select(Investigation).where(Investigation.match_id == match.id, Investigation.pharmacy_id == pharmacy.id)) or Investigation(pharmacy_id=pharmacy.id, match_id=match.id)
    record.status, record.note = data.status, data.note
    db.add(record)
    db.flush()
    db.add(AuditEvent(pharmacy_id=pharmacy.id, actor_id=user, action="investigation_" + data.status, entity_id=record.id, detail={"note": data.note}))
    db.commit()
    return fields(record, ["id", "match_id", "status", "note", "updated_at"])


@app.get("/api/investigations/{record_id}/events")
def investigation_events(record_id: str, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = pharmacy_for(db, user)
    record = db.scalar(select(Investigation).where(Investigation.id == record_id, Investigation.pharmacy_id == pharmacy.id))
    if not record:
        raise HTTPException(404, "Investigation not found")
    return [fields(e, ["id", "actor_id", "action", "detail", "created_at"]) for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_id == record.id, AuditEvent.pharmacy_id == pharmacy.id).order_by(AuditEvent.created_at))]


@app.get("/api/ingestion/status")
def ingestion_status(user: str = Depends(current_user), db: Session = Depends(get_db)):
    latest = db.scalar(select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(1))
    success = db.scalar(select(IngestionRun).where(IngestionRun.status == "succeeded").order_by(desc(IngestionRun.finished_at)).limit(1))
    return {"state": latest.status if latest else "never_synced", "last_checked": success.finished_at if success else None, "record_count": success.record_count if success else 0, "source_url": SOURCE_URL, "error": latest.error if latest else ""}


class KeyInput(BaseModel):
    api_key: str = Field(min_length=12, max_length=500)


@app.get("/api/integrations/tinyfish")
def connection(user: str = Depends(current_user), db: Session = Depends(get_db)):
    entry = db.scalar(select(TinyfishConnection).where(TinyfishConnection.user_id == user))
    return {"connected": bool(entry), "fingerprint": entry.fingerprint if entry else None, "status": entry.status if entry else "disconnected", "last_verified_at": entry.last_verified_at if entry else None}


@app.post("/api/integrations/tinyfish")
def connect(data: KeyInput, user: str = Depends(current_user), db: Session = Depends(get_db)):
    entry = db.scalar(select(TinyfishConnection).where(TinyfishConnection.user_id == user)) or TinyfishConnection(user_id=user)
    entry.encrypted_key = encrypt(data.api_key)
    entry.fingerprint = key_fingerprint(data.api_key)
    entry.status = "connected"
    db.add(entry)
    db.commit()
    return connection(user, db)


@app.delete("/api/integrations/tinyfish")
def disconnect(user: str = Depends(current_user), db: Session = Depends(get_db)):
    entry = db.scalar(select(TinyfishConnection).where(TinyfishConnection.user_id == user))
    if entry:
        db.delete(entry)
        db.commit()
    return {"connected": False}


@app.post("/api/integrations/tinyfish/test")
def test_connection(user: str = Depends(current_user), db: Session = Depends(get_db)):
    entry = db.scalar(select(TinyfishConnection).where(TinyfishConnection.user_id == user))
    if not entry:
        raise HTTPException(404, "Connect a TinyFish key first")
    try:
        response = httpx.get("https://api.search.tinyfish.ai", params={"query": "CDSCO"}, headers={"X-API-Key": decrypt(entry.encrypted_key)}, timeout=15)
        if response.status_code in (401, 403):
            entry.status = "invalid"
            db.commit()
            raise HTTPException(400, "TinyFish rejected this API key")
        if response.status_code == 429:
            raise HTTPException(429, "TinyFish rate limit reached")
        response.raise_for_status()
        entry.status = "connected"
        entry.last_verified_at = datetime.now(timezone.utc)
        db.commit()
        return {"stored": True, "provider_verified": True, "message": "TinyFish accepted this key on its Search API. Browser-agent credits are checked during sync."}
    except HTTPException:
        raise
    except httpx.HTTPError as exc:
        raise HTTPException(502, "TinyFish connection could not be verified") from exc


class SyncInput(BaseModel):
    period: str = Field(pattern="^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-20[0-9]{2}$")
    limit: int = Field(default=10, ge=1, le=25)
    account: str = Field(default="mine", pattern="^(mine|service)$")


@app.post("/api/ingestion/sync")
def sync(data: SyncInput, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy_for(db, user)
    if data.account != "mine":
        raise HTTPException(403, "Service ingestion is not available from user accounts")
    entry = db.scalar(select(TinyfishConnection).where(TinyfishConnection.user_id == user))
    if not entry:
        raise HTTPException(409, "Connect your own TinyFish key first")
    recent = db.scalar(select(IngestionRun).where(IngestionRun.requesting_user_id == user, IngestionRun.started_at > datetime.now(timezone.utc) - timedelta(minutes=10)).order_by(desc(IngestionRun.started_at)).limit(1))
    if recent:
        raise HTTPException(429, "Wait 10 minutes between TinyFish runs")
    run = IngestionRun(requesting_user_id=user, connection_id=entry.id, period=data.period)
    db.add(run)
    db.commit()
    try:
        records, provider_run = retrieve(decrypt(entry.encrypted_key), data.period, data.limit)
        store_records(db, records, run.id)
        run.status = "succeeded"
        run.provider_run_id = provider_run
        run.record_count = len(records)
        run.finished_at = datetime.now(timezone.utc)
        entry.last_verified_at = run.finished_at
        db.commit()
        for pharmacy in db.scalars(select(Pharmacy)):
            rerun(db, pharmacy)
        return {"run_id": run.id, "provider_run_id": provider_run, "status": run.status, "record_count": run.record_count}
    except Exception as exc:
        run.status = "failed"
        run.error = "Provider or source retrieval failed; inspect server logs without credentials"
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(502, run.error) from exc


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
