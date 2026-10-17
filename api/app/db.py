from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_schema(target_engine=engine):
    Base.metadata.create_all(bind=target_engine)
    # Repair the one known pre-provenance local schema without resetting user data.
    if target_engine.dialect.name == "sqlite":
        inspector = inspect(target_engine)
        if inspector.has_table("ingestion_runs") and "provider_run_id" not in {column["name"] for column in inspector.get_columns("ingestion_runs")}:
            with target_engine.begin() as connection:
                connection.execute(text("ALTER TABLE ingestion_runs ADD COLUMN provider_run_id VARCHAR(100)"))


def get_db():
    with SessionLocal() as db:
        yield db
