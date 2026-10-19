from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


config = settings()
database_url = config.database_url
engine_options = {"pool_pre_ping": True}
if database_url.startswith("postgresql"):
    # Keep the small production pool bounded, but do not force TLS against the
    # local docker-compose Postgres instance. Remote databases still default to
    # sslmode=require unless the URL or DB_SSLMODE explicitly says otherwise.
    connect_args = {"connect_timeout": 10}
    if config.resolved_db_sslmode:
        connect_args["sslmode"] = config.resolved_db_sslmode
    engine_options.update(
        pool_size=2,
        max_overflow=0,
        pool_timeout=10,
        pool_recycle=1800,
        connect_args=connect_args,
    )
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_schema(target_engine=engine):
    if target_engine.dialect.name == "postgresql":
        # PostgreSQL schema and grants are changed by reviewed migrations, not
        # implicitly on API startup. The browser uses Supabase Auth only; app
        # data is accessed through the pharmacy-scoped API.
        inspector = inspect(target_engine)
        required_columns = {
            "monitoring_notifications": {
                "id", "pharmacy_id", "event_id", "inventory_id", "alert_id",
                "status", "title", "message", "is_read", "is_active", "created_at",
            },
            "ingestion_runs": {
                "provider_run_id", "provider_run_url", "source_kind", "retrieval_metadata",
            },
        }
        missing = []
        for table_name, columns in required_columns.items():
            if not inspector.has_table(table_name):
                missing.append(f"table {table_name}")
                continue
            present = {column["name"] for column in inspector.get_columns(table_name)}
            missing.extend(f"{table_name}.{column}" for column in sorted(columns - present))
        if missing:
            raise RuntimeError(
                "PostgreSQL schema is missing required migrations 001/002: "
                + ", ".join(missing)
            )
        return

    if target_engine.dialect.name != "sqlite":
        raise RuntimeError("Only local SQLite and migrated PostgreSQL are supported")

    Base.metadata.create_all(bind=target_engine)
    # Repair local SQLite files without resetting user data.
    inspector = inspect(target_engine)
    if inspector.has_table("ingestion_runs"):
        run_columns = {column["name"] for column in inspector.get_columns("ingestion_runs")}
        with target_engine.begin() as connection:
            if "provider_run_id" not in run_columns:
                connection.execute(text("ALTER TABLE ingestion_runs ADD COLUMN provider_run_id VARCHAR(100)"))
            if "provider_run_url" not in run_columns:
                connection.execute(text("ALTER TABLE ingestion_runs ADD COLUMN provider_run_url VARCHAR(500) NOT NULL DEFAULT ''"))
            if "source_kind" not in run_columns:
                connection.execute(text("ALTER TABLE ingestion_runs ADD COLUMN source_kind VARCHAR(32) NOT NULL DEFAULT 'unknown'"))
            if "retrieval_metadata" not in run_columns:
                connection.execute(text("ALTER TABLE ingestion_runs ADD COLUMN retrieval_metadata JSON NOT NULL DEFAULT '{}'"))
    if inspector.has_table("monitoring_notifications"):
        notification_columns = {column["name"] for column in inspector.get_columns("monitoring_notifications")}
        with target_engine.begin() as connection:
            if "is_active" not in notification_columns:
                connection.execute(text(
                    "ALTER TABLE monitoring_notifications "
                    "ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1"
                ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_monitoring_notifications_pharmacy_id "
                "ON monitoring_notifications (pharmacy_id)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_monitoring_notifications_pharmacy_active_created "
                "ON monitoring_notifications (pharmacy_id, is_active, created_at)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS "
                "ix_monitoring_notifications_pharmacy_unread_active "
                "ON monitoring_notifications (pharmacy_id, is_active, is_read)"
            ))


def get_db():
    with SessionLocal() as db:
        yield db
