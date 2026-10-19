from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.db import initialize_schema


def test_existing_local_sqlite_database_receives_missing_run_provenance_column():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE ingestion_runs (id VARCHAR(36) PRIMARY KEY)"))
    initialize_schema(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("ingestion_runs")}
    assert {"provider_run_id", "provider_run_url", "source_kind", "retrieval_metadata"}.issubset(columns)
    initialize_schema(engine)


def test_existing_local_notification_rows_gain_active_state_and_indexes():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as db:
        db.execute(text("""
            CREATE TABLE monitoring_notifications (
                id VARCHAR(36) PRIMARY KEY,
                pharmacy_id VARCHAR(36) NOT NULL,
                event_id VARCHAR(64) NOT NULL,
                inventory_id VARCHAR(36) NOT NULL,
                alert_id VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL DEFAULT '',
                is_read BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL
            )
        """))
        db.execute(text("""
            INSERT INTO monitoring_notifications
                (id, pharmacy_id, event_id, inventory_id, alert_id, status, title, message, is_read, created_at)
            VALUES ('n1', 'p1', 'e1', 'i1', 'a1', 'needs_verification', 'Existing', 'Keep me', 1, CURRENT_TIMESTAMP)
        """))
    initialize_schema(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("monitoring_notifications")}
    indexes = {index["name"] for index in inspect(engine).get_indexes("monitoring_notifications")}
    assert "is_active" in columns
    assert {
        "ix_monitoring_notifications_pharmacy_id",
        "ix_monitoring_notifications_pharmacy_active_created",
        "ix_monitoring_notifications_pharmacy_unread_active",
    }.issubset(indexes)
    with engine.connect() as db:
        row = db.execute(text("SELECT is_read, is_active, message FROM monitoring_notifications WHERE id='n1'")).one()
    assert row.is_read == 1
    assert row.is_active == 1
    assert row.message == "Keep me"
