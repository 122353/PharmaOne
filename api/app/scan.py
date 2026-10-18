"""Packaging extraction and pharmacist-confirmed alert lookup."""
from datetime import datetime, timedelta, timezone
import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from PIL import Image, UnidentifiedImageError

from .auth import current_user
from .config import settings
from .db import get_db
from .matching import compare
from .ml import pharma_classify
from .models import Alert, AuditEvent, Pharmacy
from .sarvam import SarvamClient, SarvamError

router = APIRouter()


def sarvam_service():
    return SarvamClient(settings().sarvam_api_key) if settings().sarvam_api_key else None


def pharmacy_for(db: Session, user: str) -> Pharmacy:
    pharmacy = db.scalar(select(Pharmacy).where(Pharmacy.owner_id == user))
    if not pharmacy:
        raise HTTPException(404, "Create your pharmacy profile first")
    return pharmacy


class ConfirmedScan(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=255)
    manufacturer: str = Field(default="", max_length=255)
    batch_number: str = Field(default="", max_length=120)
    strength: str = Field(default="", max_length=100)
    manufacturing_date: str = Field(default="", max_length=30)
    expiry_date: str = Field(default="", max_length=30)
    confirmed: bool


@router.post("/api/scan/match")
def scan_match(data: ConfirmedScan, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy_for(db, user)
    if not data.confirmed:
        raise HTTPException(400, "Confirm the extracted identifiers before matching")
    item = data.model_dump()
    matches = []
    for alert in db.scalars(select(Alert).order_by(Alert.retrieved_at.desc()).limit(2000)):
        record = {"product_name": alert.product_name, "manufacturer": alert.manufacturer,
                  "batch_number": alert.batch_number}
        status, explanation = compare(item, record)
        if status != "no_identified_match":
            matches.append({"status": status, "explanation": explanation,
                            "alert": {"fingerprint": alert.fingerprint, "product_name": alert.product_name,
                                      "manufacturer": alert.manufacturer, "batch_number": alert.batch_number,
                                      "quality_issue": alert.quality_issue, "source_url": alert.source_url,
                                      "reporting_period": alert.reporting_period,
                                      "pharma_classify": pharma_classify(alert.quality_issue)}})
    return {"matches": matches[:20], "confirmed_identifiers": item,
            "note": "Potential matches require physical pharmacist verification. No inventory or hold was changed."}


@router.post("/api/scan/ocr")
async def scan_ocr(file: UploadFile = File(...), user: str = Depends(current_user),
                   db: Session = Depends(get_db), provider=Depends(sarvam_service)):
    pharmacy = pharmacy_for(db, user)
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024 or not raw:
        raise HTTPException(400, "Image must be 5 MB or smaller")
    mime = "image/png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg" if raw.startswith(b"\xff\xd8\xff") else ""
    if not mime or file.content_type not in (mime, "application/octet-stream"):
        raise HTTPException(400, "Upload a PNG or JPEG image")
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 20_000_000 or image.format not in ("PNG", "JPEG"):
                raise ValueError()
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, "Image file is invalid or too large") from None
    if provider is None:
        raise HTTPException(503, "Sarvam OCR is not configured")
    used = db.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.pharmacy_id == pharmacy.id, AuditEvent.action == "scan_ocr",
        AuditEvent.created_at >= datetime.now(timezone.utc) - timedelta(days=1))) or 0
    if used >= 10:
        raise HTTPException(429, "Daily OCR limit reached")
    db.add(AuditEvent(pharmacy_id=pharmacy.id, actor_id=user, action="scan_ocr",
                      entity_id=pharmacy.id, detail={"mime": mime, "size": len(raw)}))
    db.commit()
    try:
        result = provider.ocr(raw, file.filename or "packaging", mime)
    except SarvamError:
        raise HTTPException(502, "OCR provider could not process this image") from None
    return {**result, "requires_confirmation": True}
