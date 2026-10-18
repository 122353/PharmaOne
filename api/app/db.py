from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


database_url = settings().database_url
engine_options = {"pool_pre_ping": True}
if database_url.startswith("postgresql"):
    # Render Free has one small API worker; keep Supabase session-pooler use bounded.
    engine_options.update(pool_size=2, max_overflow=0, pool_timeout=10, pool_recycle=1800,
                          connect_args={"connect_timeout": 10, "sslmode": "require"})
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def initialize_schema(target_engine=engine):
    Base.metadata.create_all(bind=target_engine)
    if target_engine.dialect.name == "postgresql":
        # The browser uses Supabase Auth only; all application data is served by
        # FastAPI's owner-scoped endpoints. Deny direct Data API access, including
        # on newly added tables. Names come solely from our model metadata.
        with target_engine.begin() as connection:
            client_roles = {row[0] for row in connection.execute(text("select rolname from pg_roles where rolname in ('anon', 'authenticated')"))}
            for table in Base.metadata.tables.values():
                name = table.name
                connection.execute(text(f'ALTER TABLE public."{name}" ENABLE ROW LEVEL SECURITY'))
                connection.execute(text(f'REVOKE ALL ON TABLE public."{name}" FROM PUBLIC'))
                for role in sorted(client_roles):
                    connection.execute(text(f'REVOKE ALL ON TABLE public."{name}" FROM "{role}"'))
    # Repair the one known pre-provenance local schema without resetting user data.
    if target_engine.dialect.name == "sqlite":
        inspector = inspect(target_engine)
        if inspector.has_table("ingestion_runs") and "provider_run_id" not in {column["name"] for column in inspector.get_columns("ingestion_runs")}:
            with target_engine.begin() as connection:
                connection.execute(text("ALTER TABLE ingestion_runs ADD COLUMN provider_run_id VARCHAR(100)"))


def get_db():
    with SessionLocal() as db:
        yield db
