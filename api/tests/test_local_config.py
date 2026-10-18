import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError
from app.config import Settings


script = Path(__file__).resolve().parents[2] / "scripts/configure_local.py"
spec = importlib.util.spec_from_file_location("configure_local", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_session_pooler_url_encodes_password_and_enforces_tls():
    template = "postgresql://postgres.project:[YOUR-PASSWORD]@region.pooler.supabase.com:5432/postgres"
    result = module.database_url(template, "a#b@ c")
    assert "a%23b%40%20c" in result
    assert "[YOUR-PASSWORD]" not in result
    assert result.startswith("postgresql+psycopg://")
    assert result.endswith("?sslmode=require")


def test_local_setup_rejects_wrong_database_uri():
    with pytest.raises(ValueError):
        module.database_url("postgresql://postgres:secret@localhost:5432/postgres", "ignored")


def test_public_deployment_rejects_sqlite_or_insecure_origins():
    base = dict(_env_file=None, pharmaone_env="production", supabase_url="https://example.supabase.co")
    with pytest.raises(ValidationError, match="PostgreSQL"):
        Settings(**base, database_url="sqlite:///temporary.db", allowed_origins="https://example.vercel.app")
    with pytest.raises(ValidationError, match="exact HTTPS"):
        Settings(**base, database_url="postgresql+psycopg://example.invalid/db", allowed_origins="http://localhost:3000")
    with pytest.raises(ValidationError, match="exact HTTPS"):
        Settings(**base, database_url="postgresql+psycopg://example.invalid/db", allowed_origins="https://example.vercel.app/path")
    config = Settings(**base, database_url="postgresql+psycopg://example.invalid/db", allowed_origins="https://example.vercel.app")
    assert config.pharmaone_env == "production"
