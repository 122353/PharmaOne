from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import StaticPool

from app.db import initialize_schema


def test_existing_local_sqlite_database_receives_missing_run_provenance_column():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as db:
        db.execute(text("CREATE TABLE ingestion_runs (id VARCHAR(36) PRIMARY KEY)"))
    initialize_schema(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("ingestion_runs")}
    assert "provider_run_id" in columns
    initialize_schema(engine)
