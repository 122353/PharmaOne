import importlib.util
from pathlib import Path

import pytest


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
