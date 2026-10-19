"""Small private investigation evidence files kept in PostgreSQL."""
import io
import re

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .rate_limit import sensitive_user
from .db import get_db
from .models import AuditEvent, Investigation, InvestigationAttachment, Pharmacy

router = APIRouter()


def owner(db: Session, user: str, record_id: str) -> tuple[Pharmacy, Investigation]:
    pharmacy = db.scalar(select(Pharmacy).where(Pharmacy.owner_id == user))
    if not pharmacy:
        raise HTTPException(404, "Investigation not found")
    record = db.scalar(select(Investigation).where(Investigation.id == record_id,
                                                   Investigation.pharmacy_id == pharmacy.id))
    if not record:
        raise HTTPException(404, "Investigation not found")
    return pharmacy, record


def metadata(item: InvestigationAttachment) -> dict:
    return {"id": item.id, "filename": item.filename, "content_type": item.content_type,
            "size": len(item.content), "created_at": item.created_at}


@router.post("/api/investigations/{record_id}/attachments")
async def upload_evidence(record_id: str, file: UploadFile = File(...), user: str = Depends(sensitive_user),
                          db: Session = Depends(get_db)):
    pharmacy, record = owner(db, user, record_id)
    raw = await file.read(2 * 1024 * 1024 + 1)
    if not raw or len(raw) > 2 * 1024 * 1024:
        raise HTTPException(400, "Evidence must be 2 MB or smaller")
    detected = ("image/png" if raw.startswith(b"\x89PNG\r\n\x1a\n") else
                "image/jpeg" if raw.startswith(b"\xff\xd8\xff") else
                "application/pdf" if raw.startswith(b"%PDF-") else "")
    if not detected or file.content_type != detected:
        raise HTTPException(400, "Upload a PNG, JPEG, or PDF")
    if detected.startswith("image/"):
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.width * image.height > 20_000_000:
                    raise ValueError()
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise HTTPException(400, "Invalid image") from None
    elif b"startxref" not in raw[-2048:] or not re.search(rb"%%EOF\s*$", raw[-2048:]):
        raise HTTPException(400, "Invalid PDF")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", (file.filename or "evidence")[-180:]).strip("._") or "evidence"
    item = InvestigationAttachment(pharmacy_id=pharmacy.id, investigation_id=record.id,
                                   filename=name, content_type=detected, content=raw)
    db.add(item)
    db.flush()
    db.add(AuditEvent(pharmacy_id=pharmacy.id, actor_id=user, action="investigation_attachment_added",
                      entity_id=record.id, detail={"attachment_id": item.id, "filename": name}))
    db.commit()
    return metadata(item)


@router.get("/api/investigations/{record_id}/attachments")
def list_evidence(record_id: str, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy, record = owner(db, user, record_id)
    return [metadata(item) for item in db.scalars(select(InvestigationAttachment).where(
        InvestigationAttachment.pharmacy_id == pharmacy.id,
        InvestigationAttachment.investigation_id == record.id).order_by(InvestigationAttachment.created_at))]


@router.get("/api/investigations/attachments/{attachment_id}")
def download_evidence(attachment_id: str, user: str = Depends(current_user), db: Session = Depends(get_db)):
    pharmacy = db.scalar(select(Pharmacy).where(Pharmacy.owner_id == user))
    if not pharmacy:
        raise HTTPException(404, "Attachment not found")
    item = db.scalar(select(InvestigationAttachment).where(InvestigationAttachment.id == attachment_id,
                                                          InvestigationAttachment.pharmacy_id == pharmacy.id))
    if not item:
        raise HTTPException(404, "Attachment not found")
    return Response(content=item.content, media_type=item.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{item.filename}"',
                             "X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
