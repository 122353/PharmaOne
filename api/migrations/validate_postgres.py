"""Opt-in local PostgreSQL migration validation; never imports app configuration.

Creates randomly named databases and retains them for inspection. It never
drops, truncates, resets, or migrates the supplied maintenance database.
"""
import os
from pathlib import Path
import re
from uuid import uuid4

from sqlalchemy.engine import make_url


def validate_test_target(raw_url, enabled):
    if enabled != "1":
        raise ValueError("Explicit local migration validation opt-in is required")
    try:
        target = make_url(raw_url)
    except Exception:
        raise ValueError("A dedicated local PostgreSQL test URL is required") from None
    if (
        target.drivername not in {"postgresql", "postgresql+psycopg"}
        or target.host not in {"127.0.0.1", "::1"}
        or not target.username
        or target.query
        or not re.fullmatch(r"pharmaone_migration_test_[a-z0-9_]{1,30}", target.database or "")
        or "#" in raw_url
        or (target.port is not None and not 1 <= target.port <= 65535)
    ):
        raise ValueError("Target must be an explicit loopback PostgreSQL disposable test database")
    return target


def _connect(target):
    import psycopg

    # Explicit connection fields prevent host/service/query URL overrides.
    return psycopg.connect(
        host=target.host, hostaddr=target.host, port=target.port or 5432,
        dbname=target.database, user=target.username, password=target.password or "",
        passfile=os.devnull, sslmode="disable", connect_timeout=5,
        application_name="pharmaone_local_migration_validation", autocommit=True,
        options="-c statement_timeout=15000 -c lock_timeout=3000",
    )


def _require(condition, description):
    if not condition:
        raise RuntimeError(description)


def _verify_server(connection, target):
    actual_database, address = connection.execute(
        "SELECT current_database(), host(inet_server_addr())"
    ).fetchone()

    is_local = address in {"127.0.0.1", "::1"}

    container_name = os.getenv(
        "PHARMAONE_MIGRATION_TEST_DOCKER_CONTAINER", ""
    )

    if not is_local and re.fullmatch(
        r"pharmaone-pg-test-[0-9]{8}", container_name
    ):
        import json
        import subprocess

        result = subprocess.run(
            ["docker", "inspect", container_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )

        info = json.loads(result.stdout)[0]
        network = info["NetworkSettings"]

        container_ips = {
            details["IPAddress"]
            for details in network["Networks"].values()
        }

        bindings = network["Ports"].get("5432/tcp") or []

        is_local = (
            address in container_ips
            and any(
                binding["HostIp"] == "127.0.0.1"
                and binding["HostPort"] == str(target.port or 5432)
                for binding in bindings
            )
        )

    _require(
        actual_database == target.database and is_local,
        "Server identity must match the guarded local test target",
    )

BASELINE = """
CREATE TABLE public.pharmacies (id VARCHAR(36) PRIMARY KEY, owner_id VARCHAR(64) UNIQUE NOT NULL, name VARCHAR(160) NOT NULL);
CREATE TABLE public.inventory_items (id VARCHAR(36) PRIMARY KEY, pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id), medicine_name VARCHAR(255) NOT NULL, batch_number VARCHAR(100) NOT NULL, manufacturer VARCHAR(255) NOT NULL, quantity INTEGER NOT NULL, CONSTRAINT uq_stock_identity UNIQUE(pharmacy_id, medicine_name, batch_number, manufacturer));
CREATE TABLE public.regulatory_alerts (fingerprint VARCHAR(64) PRIMARY KEY, product_name VARCHAR(500) NOT NULL, raw_record JSON NOT NULL);
CREATE TABLE public.inventory_alert_matches (id VARCHAR(36) PRIMARY KEY, pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id), inventory_id VARCHAR(36) NOT NULL REFERENCES public.inventory_items(id), alert_id VARCHAR(64) NOT NULL REFERENCES public.regulatory_alerts(fingerprint), status VARCHAR(32) NOT NULL, CONSTRAINT uq_match_pair UNIQUE(inventory_id, alert_id));
CREATE TABLE public.investigations (id VARCHAR(36) PRIMARY KEY, pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id), match_id VARCHAR(36) NOT NULL UNIQUE REFERENCES public.inventory_alert_matches(id), note TEXT NOT NULL);
CREATE TABLE public.ingestion_runs (id VARCHAR(36) PRIMARY KEY, provider_run_id VARCHAR(100) NOT NULL, period VARCHAR(20) NOT NULL, status VARCHAR(24) NOT NULL);
INSERT INTO public.pharmacies VALUES ('p1', 'owner1', 'Retained pharmacy');
INSERT INTO public.inventory_items VALUES ('i1', 'p1', 'Retained medicine', 'b1', 'Maker', 7);
INSERT INTO public.regulatory_alerts VALUES ('a1', 'Retained alert', '{"evidence":"keep"}');
INSERT INTO public.inventory_alert_matches VALUES ('m1', 'p1', 'i1', 'a1', 'needs_verification');
INSERT INTO public.investigations VALUES ('v1', 'p1', 'm1', 'Retained investigation');
INSERT INTO public.ingestion_runs VALUES ('r1', 'provider1', '2026-01', 'completed');
"""

PROTOTYPE = """
CREATE TABLE public.monitoring_notifications (
 id VARCHAR(36) PRIMARY KEY,
 pharmacy_id VARCHAR(36) NOT NULL REFERENCES public.pharmacies(id),
 event_id VARCHAR(64) NOT NULL,
 inventory_id VARCHAR(36) NOT NULL REFERENCES public.inventory_items(id),
 alert_id VARCHAR(64) NOT NULL REFERENCES public.regulatory_alerts(fingerprint),
 status VARCHAR(32) NOT NULL, title VARCHAR(255) NOT NULL,
 message TEXT NOT NULL DEFAULT '', is_read BOOLEAN NOT NULL DEFAULT FALSE,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
 {unique_constraint}
);
INSERT INTO public.monitoring_notifications
 (id, pharmacy_id, event_id, inventory_id, alert_id, status, title, message, is_read)
 VALUES ('n1', 'p1', 'e1', 'i1', 'a1', 'needs_verification', 'Retained', 'Keep this notification', TRUE);
"""


def _snapshot(connection):
    result = {}
    for table in ("pharmacies", "inventory_items", "regulatory_alerts",
                  "inventory_alert_matches", "investigations"):
        # Table names are fixed source literals; values are synthetic fixtures.
        result[table] = connection.execute(f"SELECT row_to_json(t)::text FROM public.{table} t").fetchall()
    result["ingestion_runs"] = connection.execute(
        "SELECT id, provider_run_id, period, status FROM public.ingestion_runs ORDER BY id"
    ).fetchall()
    return result


def _apply(connection):
    for filename in ("001_monitoring_notifications.sql", "002_ingestion_run_provenance.sql"):
        connection.execute((Path(__file__).parent / filename).read_text(encoding="utf-8"))


def _assert_constraint_rejected(connection, statement, sqlstate):
    import psycopg

    try:
        with connection.transaction():
            connection.execute(statement)
    except psycopg.Error as error:
        _require(error.sqlstate == sqlstate, "Unexpected constraint failure")
    else:
        raise RuntimeError("Expected constraint was not enforced")


def _assert_ready(connection):
    columns = connection.execute("""
        SELECT column_name, data_type, is_nullable FROM information_schema.columns
        WHERE table_schema='public' AND table_name='ingestion_runs'
          AND column_name IN ('provider_run_url','source_kind','retrieval_metadata')
    """).fetchall()
    _require(set(columns) == {("provider_run_url", "character varying", "NO"),
                             ("source_kind", "character varying", "NO"),
                             ("retrieval_metadata", "json", "NO")}, "Provenance schema mismatch")
    _require(connection.execute("SELECT provider_run_url, source_kind, retrieval_metadata FROM public.ingestion_runs WHERE id='r1'").fetchone()
             == ("", "unknown", {}), "Existing ingestion run provenance defaults changed")
    indexes = dict(connection.execute("""
        SELECT indexrelid::regclass::text, pg_get_indexdef(indexrelid)
        FROM pg_index WHERE indrelid='public.monitoring_notifications'::regclass
          AND indisvalid AND indisready
    """).fetchall())
    for name, definition in {
        "ix_monitoring_notifications_pharmacy_id": "(pharmacy_id)",
        "ix_monitoring_notifications_pharmacy_active_created": "(pharmacy_id, is_active, created_at)",
        "ix_monitoring_notifications_pharmacy_unread_active": "(pharmacy_id, is_active, is_read)",
    }.items():
        _require(definition in indexes.get(name, ""), "Notification index missing or has incorrect columns")
    _require(connection.execute("SELECT relrowsecurity FROM pg_class WHERE oid='public.monitoring_notifications'::regclass").fetchone() == (True,), "Notification RLS is disabled")
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        _require(connection.execute("SELECT has_table_privilege(current_user,'public.monitoring_notifications',%s)", (privilege,)).fetchone() == (True,), "Fixture migration owner lacks runtime DML privileges")
    _require(connection.execute("SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename='monitoring_notifications'").fetchone() == (0,), "Unexpected notification client policy")
    _require(connection.execute("""
        SELECT count(*) FROM pg_class c,
        LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) a
        WHERE c.oid='public.monitoring_notifications'::regclass AND a.grantee=0
    """).fetchone() == (0,), "PUBLIC has notification privileges")
    roles = [row[0] for row in connection.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")]
    for role in roles:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            _require(connection.execute("SELECT has_table_privilege(%s,'public.monitoring_notifications',%s)", (role, privilege)).fetchone() == (False,), "Client role retains notification privileges")
    connection.execute("""INSERT INTO public.monitoring_notifications
        (id,pharmacy_id,event_id,inventory_id,alert_id,status,title)
        VALUES ('valid','p1','valid','i1','a1','needs_verification','Valid')""")
    _assert_constraint_rejected(connection, "INSERT INTO public.monitoring_notifications SELECT * FROM public.monitoring_notifications WHERE id='valid'", "23505")
    _assert_constraint_rejected(connection, "INSERT INTO public.monitoring_notifications (id,pharmacy_id,event_id,inventory_id,alert_id,status,title) VALUES ('valid','p1','different-event','i1','a1','s','t')", "23505")
    for field in ("pharmacy_id", "inventory_id", "alert_id"):
        _assert_constraint_rejected(connection, f"UPDATE public.monitoring_notifications SET {field}='missing' WHERE id='valid'", "23503")
    _assert_constraint_rejected(connection, "UPDATE public.monitoring_notifications SET pharmacy_id=NULL WHERE id='valid'", "23502")
    _assert_constraint_rejected(connection, "INSERT INTO public.monitoring_notifications (id,pharmacy_id,event_id,inventory_id,alert_id,status,title) VALUES ('other','p1','valid','i1','a1','s','t')", "23505")
    return roles


def run_validation(raw_url, enabled):
    target = validate_test_target(raw_url, enabled)
    from psycopg import sql

    databases = []
    checks = []
    roles = []
    # The maintenance DB is read only except CREATE DATABASE at cluster level.
    with _connect(target) as maintenance:
        _verify_server(maintenance, target)
        for scenario in ("fresh", "compatible", "missing_unique", "missing_pk", "missing_fk", "wrong_index", "wrong_provenance"):
            database = "pharmaone_migration_test_" + uuid4().hex[:20]
            maintenance.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(database)))
            databases.append(database)
            with _connect(target.set(database=database)) as connection:
                _verify_server(connection, target.set(database=database))
                connection.execute(BASELINE)
                client_roles = [row[0] for row in connection.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")]
                # Seed permissive defaults so deleting REVOKE from the migration
                # cannot accidentally pass on PostgreSQL's already-private ACLs.
                connection.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC")
                for role in client_roles:
                    connection.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {}").format(sql.Identifier(role)))
                if scenario != "fresh":
                    constraint = "" if scenario == "missing_unique" else ", CONSTRAINT uq_monitoring_notification_event UNIQUE(pharmacy_id,event_id)"
                    prototype = PROTOTYPE.format(unique_constraint=constraint)
                    if scenario == "missing_pk":
                        prototype = prototype.replace("id VARCHAR(36) PRIMARY KEY", "id VARCHAR(36) NOT NULL", 1)
                    if scenario == "missing_fk":
                        prototype = prototype.replace(" REFERENCES public.inventory_items(id)", "")
                    connection.execute(prototype)
                    if scenario == "wrong_index":
                        connection.execute("CREATE INDEX ix_monitoring_notifications_pharmacy_id ON public.monitoring_notifications(event_id)")
                    if scenario == "wrong_provenance":
                        connection.execute("ALTER TABLE public.ingestion_runs ADD COLUMN source_kind INTEGER")
                before = _snapshot(connection)
                if scenario not in {"fresh", "compatible"}:
                    try:
                        _apply(connection)
                    except Exception as error:
                        connection.execute("ROLLBACK")
                        _require(getattr(error, "sqlstate", None) == "23514", "Incompatible prototype must fail with a readiness error")
                        _require(_snapshot(connection) == before, "Failed migration changed retained records")
                        if scenario != "wrong_provenance":
                            _require(connection.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='monitoring_notifications' AND column_name='is_active'").fetchone() == (0,), "Failed migration did not roll back additive DDL")
                        else:
                            # 001 committed successfully; 002 is its own atomic migration.
                            _require(connection.execute("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='ingestion_runs' AND column_name='provider_run_url'").fetchone() == (0,), "Failed provenance migration did not roll back additive DDL")
                    else:
                        raise RuntimeError("Migration accepted an incompatible prototype")
                    if scenario == "wrong_provenance":
                        checks.append("incompatible_prototypes_fail_closed")
                    continue
                _apply(connection)
                _apply(connection)
                _require(_snapshot(connection) == before, "Migration changed retained records")
                if scenario == "fresh":
                    checks.append("fresh_apply_twice_preserves_rows")
                    roles = _assert_ready(connection)
                    checks.append("foreign_keys_unique_indexes_rls_grants")
                else:
                    _require(connection.execute("SELECT is_read,is_active,message FROM public.monitoring_notifications WHERE id='n1'").fetchone()
                             == (True, True, "Keep this notification"), "Prototype notification changed")
                    _assert_ready(connection)
                    checks.append("compatible_prototype_preserves_notification")
    return {"checks": checks, "retained_databases": databases,
            "client_roles_checked": roles, "client_roles_absent": sorted({"anon", "authenticated"} - set(roles))}


if __name__ == "__main__":
    import json
    try:
        result = run_validation(os.getenv("PHARMAONE_MIGRATION_TEST_URL", ""),
                                os.getenv("PHARMAONE_RUN_LOCAL_PG_MIGRATIONS", ""))
    except Exception as error:
        # Connection errors may contain credentials; never print the exception/URL.
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__,
                          "detail": "Local validation failed; review configuration and retained fixture databases"}))
        raise SystemExit(1)
    print(json.dumps({"status": "PASSED", **result}, indent=2))
