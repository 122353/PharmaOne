"""Local target guards always run; real PostgreSQL checks require explicit opt-in."""
import importlib.util
from pathlib import Path
import os

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "migrations" / "validate_postgres.py"
spec = importlib.util.spec_from_file_location("migration_validation", MODULE_PATH)
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


@pytest.mark.parametrize("url,enabled", [
    ("postgresql://127.0.0.1/pharmaone_migration_test_local", "0"),
    ("postgresql://db.example.com/pharmaone_migration_test_local", "1"),
    ("postgresql://localhost/pharmaone_migration_test_local", "1"),
    ("postgresql://127.0.0.1/pharmaone", "1"),
    ("postgresql://127.0.0.1/postgres", "1"),
    ("sqlite:///pharmaone_migration_test_local", "1"),
    ("postgresql:///pharmaone_migration_test_local", "1"),
    ("postgresql://127.0.0.1/pharmaone_migration_test_local?host=production", "1"),
    ("postgresql://127.0.0.1/pharmaone_migration_test_local#fragment", "1"),
    ("postgresql://127.0.0.1/pharmaone_migration_test_local/other", "1"),
])
def test_target_guard_rejects_unsafe_targets_before_connecting(url, enabled, monkeypatch):
    def unexpected_connection(_target):
        raise AssertionError("Unsafe target reached database connection")

    monkeypatch.setattr(validation, "_connect", unexpected_connection)
    with pytest.raises(ValueError):
        validation.run_validation(url, enabled)


@pytest.mark.parametrize("host", ["127.0.0.1", "[::1]"])
def test_target_guard_accepts_explicit_loopback_disposable_database(host):
    target = validation.validate_test_target(
        f"postgresql://tester@{host}:5432/pharmaone_migration_test_local", "1"
    )
    assert target.database == "pharmaone_migration_test_local"


def test_missing_test_url_never_falls_back_to_application_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://app@remote.invalid/production")
    with pytest.raises(ValueError):
        validation.run_validation("", "1")


def test_postgres_migrations_on_isolated_seeded_databases():
    if os.getenv("PHARMAONE_RUN_LOCAL_PG_MIGRATIONS") != "1":
        pytest.skip("Requires explicit opt-in and a disposable local PostgreSQL runtime")
    result = validation.run_validation(
        os.getenv("PHARMAONE_MIGRATION_TEST_URL", ""),
        os.getenv("PHARMAONE_RUN_LOCAL_PG_MIGRATIONS", ""),
    )
    assert result["checks"] == [
        "fresh_apply_twice_preserves_rows",
        "foreign_keys_unique_indexes_rls_grants",
        "compatible_prototype_preserves_notification",
        "incompatible_prototypes_fail_closed",
    ]
