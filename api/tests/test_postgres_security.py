"""Verify exposed Supabase client roles cannot query app-owned tables directly."""
import os
import pytest
from sqlalchemy import text
from app.db import engine


@pytest.mark.skipif(os.getenv("PHARMAONE_TEST_POSTGRES") != "1" or engine.dialect.name != "postgresql", reason="Requires configured PostgreSQL")
def test_supabase_client_roles_have_no_direct_table_access():
    tables = ("pharmacies", "inventory_items", "inventory_alert_matches", "investigations", "audit_events", "tinyfish_connections", "ingestion_runs", "regulatory_alerts", "alert_versions", "supplier_links", "inventory_imports", "investigation_attachments")
    with engine.connect() as connection:
        for table in tables:
            enabled = connection.scalar(text("select relrowsecurity from pg_class where oid = to_regclass(:table)"), {"table": "public." + table})
            assert enabled is True, table
            for role in ("anon", "authenticated"):
                for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                    allowed = connection.scalar(text("select has_table_privilege(:role, :table, :privilege)"), {"role": role, "table": "public." + table, "privilege": privilege})
                    assert allowed is False, (table, role, privilege)


@pytest.mark.skipif(os.getenv("PHARMAONE_TEST_POSTGRES") != "1" or engine.dialect.name != "postgresql", reason="Requires configured PostgreSQL")
def test_central_sync_advisory_lock_excludes_overlap():
    from app.ingest_service import operator_lock
    with operator_lock():
        with engine.connect() as competing:
            assert competing.scalar(text("select pg_try_advisory_lock(730114223)")) is False
