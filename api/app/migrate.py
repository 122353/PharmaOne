"""Apply checked-in PostgreSQL migrations in filename order.

This entrypoint is explicit: the FastAPI startup path still validates schema and
never performs DDL implicitly. Use it for a fresh PostgreSQL database before
starting the API (docker-compose does this automatically).
"""
from pathlib import Path

import psycopg

from .config import settings


MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def _psycopg_dsn(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url[len("postgresql+psycopg://"):]
    return database_url


def apply_migrations() -> list[str]:
    config = settings()
    if not config.database_url.startswith("postgresql+psycopg://"):
        raise RuntimeError("PostgreSQL DATABASE_URL is required for migrations")

    connect_kwargs = {"connect_timeout": 10}
    if config.resolved_db_sslmode:
        connect_kwargs["sslmode"] = config.resolved_db_sslmode

    applied = []
    with psycopg.connect(
        _psycopg_dsn(config.database_url),
        autocommit=True,
        **connect_kwargs,
    ) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        for path in sorted(MIGRATIONS.glob("[0-9][0-9][0-9]_*.sql")):
            exists = connection.execute(
                "SELECT 1 FROM public.schema_migrations WHERE filename = %s",
                (path.name,),
            ).fetchone()
            if exists:
                continue

            # Migration files own their transactions. With autocommit enabled,
            # a failed file rolls back its own BEGIN/COMMIT block and is not
            # recorded in schema_migrations.
            connection.execute(path.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO public.schema_migrations (filename) VALUES (%s)",
                (path.name,),
            )
            applied.append(path.name)

    return applied


def main() -> int:
    applied = apply_migrations()
    if applied:
        print("Applied migrations: " + ", ".join(applied))
    else:
        print("Database schema is already up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
