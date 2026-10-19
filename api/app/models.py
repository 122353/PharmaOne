from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, UniqueConstraint, JSON, LargeBinary, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


def uid():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Pharmacy(Base):
    __tablename__ = "pharmacies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    contact_name: Mapped[str] = mapped_column(String(160), default="")
    kind: Mapped[str] = mapped_column(String(32), default="retail")
    city: Mapped[str] = mapped_column(String(100), default="")
    state: Mapped[str] = mapped_column(String(100), default="")
    inventory_format: Mapped[str] = mapped_column(String(32), default="csv")
    batch_available: Mapped[bool] = mapped_column(default=True)
    manufacturer_available: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("pharmacy_id", "medicine_name", "batch_number", "manufacturer", name="uq_stock_identity"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pharmacy_id: Mapped[str] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    medicine_name: Mapped[str] = mapped_column(String(255))
    manufacturer: Mapped[str] = mapped_column(String(255), default="")
    batch_number: Mapped[str] = mapped_column(String(100), default="", index=True)
    strength: Mapped[str] = mapped_column(String(100), default="")
    expiry_date: Mapped[str] = mapped_column(String(30), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    quality_state: Mapped[str] = mapped_column(String(32), default="needs_verification")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Alert(Base):
    __tablename__ = "regulatory_alerts"
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(500))
    manufacturer: Mapped[str] = mapped_column(String(700), default="")
    batch_number: Mapped[str] = mapped_column(String(120), default="", index=True)
    quality_issue: Mapped[str] = mapped_column(Text, default="")
    reporting_period: Mapped[str] = mapped_column(String(20))
    reporting_source: Mapped[str] = mapped_column(String(100), default="")
    source_url: Mapped[str] = mapped_column(String(500))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    run_id: Mapped[str] = mapped_column(String(36))
    raw_record: Mapped[dict] = mapped_column(JSON)
    classification: Mapped[str] = mapped_column(String(30), default="nsq")


class AlertVersion(Base):
    __tablename__ = "alert_versions"
    __table_args__ = (UniqueConstraint("alert_id", "content_hash", name="uq_alert_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    alert_id: Mapped[str] = mapped_column(ForeignKey("regulatory_alerts.fingerprint"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    quality_issue: Mapped[str] = mapped_column(Text, default="")
    raw_record: Mapped[dict] = mapped_column(JSON)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Match(Base):
    __tablename__ = "inventory_alert_matches"
    __table_args__ = (UniqueConstraint("inventory_id", "alert_id", name="uq_match_pair"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pharmacy_id: Mapped[str] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventory_items.id"))
    alert_id: Mapped[str] = mapped_column(ForeignKey("regulatory_alerts.fingerprint"))
    status: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[dict] = mapped_column(JSON)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Investigation(Base):
    __tablename__ = "investigations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pharmacy_id: Mapped[str] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("inventory_alert_matches.id"), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="open")
    note: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class SupplierLink(Base):
    """Pharmacy-entered synthetic demonstration relationship, never a source claim."""
    __tablename__ = "supplier_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pharmacy_id: Mapped[str] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    inventory_id: Mapped[str] = mapped_column(ForeignKey("inventory_items.id"), unique=True)
    supplier: Mapped[str] = mapped_column(String(160))
    distributor: Mapped[str] = mapped_column(String(160))
    synthetic: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InventoryImport(Base):
    __tablename__ = "inventory_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pharmacy_id: Mapped[str] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    source: Mapped[str] = mapped_column(String(32))
    imported: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    rejected: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InvestigationAttachment(Base):
    __tablename__ = "investigation_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pharmacy_id: Mapped[str] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    investigation_id: Mapped[str] = mapped_column(ForeignKey("investigations.id"), index=True)
    filename: Mapped[str] = mapped_column(String(180))
    content_type: Mapped[str] = mapped_column(String(50))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    pharmacy_id: Mapped[str] = mapped_column(ForeignKey("pharmacies.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(36))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class TinyfishConnection(Base):
    __tablename__ = "tinyfish_connections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    encrypted_key: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="connected")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    requesting_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connection_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    provider_run_id: Mapped[str] = mapped_column(String(100), default="")
    provider_run_url: Mapped[str] = mapped_column(String(500), default="")
    source_kind: Mapped[str] = mapped_column(String(32), default="unknown")
    retrieval_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
    period: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), default="running")
    error: Mapped[str] = mapped_column(String(300), default="")
    record_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
class MonitoringNotification(Base):
    __tablename__ = "monitoring_notifications"
    __table_args__ = (
        UniqueConstraint(
            "pharmacy_id",
            "event_id",
            name="uq_monitoring_notification_event",
        ),
        Index(
            "ix_monitoring_notifications_pharmacy_active_created",
            "pharmacy_id", "is_active", "created_at",
        ),
        Index(
            "ix_monitoring_notifications_pharmacy_unread_active",
            "pharmacy_id", "is_active", "is_read",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=uid
    )
    pharmacy_id: Mapped[str] = mapped_column(
        ForeignKey("pharmacies.id"), index=True
    )
    event_id: Mapped[str] = mapped_column(String(64))
    inventory_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_items.id")
    )
    alert_id: Mapped[str] = mapped_column(
        ForeignKey("regulatory_alerts.fingerprint")
    )
    status: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text, default="")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now
    )
