-- PharmaOne AI baseline PostgreSQL schema.
-- This file creates the core application tables required before migrations 001/002.
-- It is additive for an already-initialized compatible database.

BEGIN;

CREATE TABLE IF NOT EXISTS public.pharmacies (
    id VARCHAR(36) PRIMARY KEY,
    owner_id VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(160) NOT NULL,
    contact_name VARCHAR(160) NOT NULL DEFAULT '',
    kind VARCHAR(32) NOT NULL DEFAULT 'retail',
    city VARCHAR(100) NOT NULL DEFAULT '',
    state VARCHAR(100) NOT NULL DEFAULT '',
    inventory_format VARCHAR(32) NOT NULL DEFAULT 'csv',
    batch_available BOOLEAN NOT NULL DEFAULT TRUE,
    manufacturer_available BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.inventory_items (
    id VARCHAR(36) PRIMARY KEY,
    pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
    medicine_name VARCHAR(255) NOT NULL,
    manufacturer VARCHAR(255) NOT NULL DEFAULT '',
    batch_number VARCHAR(100) NOT NULL DEFAULT '',
    strength VARCHAR(100) NOT NULL DEFAULT '',
    expiry_date VARCHAR(30) NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 0,
    quality_state VARCHAR(32) NOT NULL DEFAULT 'needs_verification',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_stock_identity UNIQUE (pharmacy_id, medicine_name, batch_number, manufacturer)
);

CREATE TABLE IF NOT EXISTS public.regulatory_alerts (
    fingerprint VARCHAR(64) PRIMARY KEY,
    product_name VARCHAR(500) NOT NULL,
    manufacturer VARCHAR(700) NOT NULL DEFAULT '',
    batch_number VARCHAR(120) NOT NULL DEFAULT '',
    quality_issue TEXT NOT NULL DEFAULT '',
    reporting_period VARCHAR(20) NOT NULL,
    reporting_source VARCHAR(100) NOT NULL DEFAULT '',
    source_url VARCHAR(500) NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    run_id VARCHAR(36) NOT NULL,
    raw_record JSON NOT NULL,
    classification VARCHAR(30) NOT NULL DEFAULT 'nsq'
);

CREATE TABLE IF NOT EXISTS public.alert_versions (
    id VARCHAR(36) PRIMARY KEY,
    alert_id VARCHAR(64) NOT NULL REFERENCES public.regulatory_alerts(fingerprint),
    content_hash VARCHAR(64) NOT NULL,
    quality_issue TEXT NOT NULL DEFAULT '',
    raw_record JSON NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_alert_version UNIQUE (alert_id, content_hash)
);

CREATE TABLE IF NOT EXISTS public.inventory_alert_matches (
    id VARCHAR(36) PRIMARY KEY,
    pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
    inventory_id VARCHAR(36) NOT NULL REFERENCES public.inventory_items(id),
    alert_id VARCHAR(64) NOT NULL REFERENCES public.regulatory_alerts(fingerprint),
    status VARCHAR(32) NOT NULL,
    explanation JSON NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_match_pair UNIQUE (inventory_id, alert_id)
);

CREATE TABLE IF NOT EXISTS public.investigations (
    id VARCHAR(36) PRIMARY KEY,
    pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
    match_id VARCHAR(36) NOT NULL UNIQUE REFERENCES public.inventory_alert_matches(id),
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    note TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.supplier_links (
    id VARCHAR(36) PRIMARY KEY,
    pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
    inventory_id VARCHAR(36) NOT NULL UNIQUE REFERENCES public.inventory_items(id),
    supplier VARCHAR(160) NOT NULL,
    distributor VARCHAR(160) NOT NULL,
    synthetic BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.inventory_imports (
    id VARCHAR(36) PRIMARY KEY,
    pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
    source VARCHAR(32) NOT NULL,
    imported INTEGER NOT NULL DEFAULT 0,
    duplicates INTEGER NOT NULL DEFAULT 0,
    rejected INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.investigation_attachments (
    id VARCHAR(36) PRIMARY KEY,
    pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
    investigation_id VARCHAR(36) NOT NULL REFERENCES public.investigations(id),
    filename VARCHAR(180) NOT NULL,
    content_type VARCHAR(50) NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.audit_events (
    id VARCHAR(36) PRIMARY KEY,
    pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
    actor_id VARCHAR(64) NOT NULL,
    action VARCHAR(80) NOT NULL,
    entity_id VARCHAR(36) NOT NULL,
    detail JSON NOT NULL DEFAULT '{}'::json,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public.tinyfish_connections (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL UNIQUE,
    encrypted_key TEXT NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'connected',
    last_verified_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 002_ingestion_run_provenance.sql adds provider_run_url, source_kind and
-- retrieval_metadata. Keeping those changes in 002 preserves migration order.
CREATE TABLE IF NOT EXISTS public.ingestion_runs (
    id VARCHAR(36) PRIMARY KEY,
    requesting_user_id VARCHAR(64) NULL,
    connection_id VARCHAR(36) NULL,
    provider_run_id VARCHAR(100) NOT NULL DEFAULT '',
    period VARCHAR(20) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'running',
    error VARCHAR(300) NOT NULL DEFAULT '',
    record_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_pharmacies_owner_id
    ON public.pharmacies (owner_id);
CREATE INDEX IF NOT EXISTS ix_inventory_items_pharmacy_id
    ON public.inventory_items (pharmacy_id);
CREATE INDEX IF NOT EXISTS ix_inventory_items_batch_number
    ON public.inventory_items (batch_number);
CREATE INDEX IF NOT EXISTS ix_regulatory_alerts_batch_number
    ON public.regulatory_alerts (batch_number);
CREATE INDEX IF NOT EXISTS ix_alert_versions_alert_id
    ON public.alert_versions (alert_id);
CREATE INDEX IF NOT EXISTS ix_inventory_alert_matches_pharmacy_id
    ON public.inventory_alert_matches (pharmacy_id);
CREATE INDEX IF NOT EXISTS ix_investigations_pharmacy_id
    ON public.investigations (pharmacy_id);
CREATE INDEX IF NOT EXISTS ix_supplier_links_pharmacy_id
    ON public.supplier_links (pharmacy_id);
CREATE INDEX IF NOT EXISTS ix_inventory_imports_pharmacy_id
    ON public.inventory_imports (pharmacy_id);
CREATE INDEX IF NOT EXISTS ix_investigation_attachments_pharmacy_id
    ON public.investigation_attachments (pharmacy_id);
CREATE INDEX IF NOT EXISTS ix_investigation_attachments_investigation_id
    ON public.investigation_attachments (investigation_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_pharmacy_id
    ON public.audit_events (pharmacy_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_tinyfish_connections_user_id
    ON public.tinyfish_connections (user_id);

COMMIT;
