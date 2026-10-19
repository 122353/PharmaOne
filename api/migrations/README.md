# PostgreSQL notifications and provenance migrations

`001_monitoring_notifications.sql` adds pharmacy notifications, a primary key, three foreign keys, unique `(pharmacy_id, event_id)`, and indexes for pharmacy/active/unread queries. It adds `is_active` to a compatible older notification table, enables RLS, and revokes table privileges from `PUBLIC` and existing `anon`/`authenticated` roles. `002_ingestion_run_provenance.sql` adds `provider_run_url`, `source_kind`, and JSON `retrieval_metadata` with defaults for retained runs.

Both files use individual transactions. Repeat application is supported for compatible schemas. No existing rows are deleted or rewritten. Adding columns with defaults changes the shape of returned rows and gives old rows the documented defaults. Locks during DDL can block concurrent writes; schedule a reviewed change window.

## Execution status (2026-10-19)

**BLOCKED: actual PostgreSQL execution has not run.** PostgreSQL binaries are absent from PATH, `C:\Program Files\PostgreSQL` is absent, and Docker's `dockerDesktopLinuxEngine` pipe is unavailable. SQL review, Python compilation, and target guard tests ran locally. SQLite tests do not establish PostgreSQL readiness. The added PostgreSQL catalog checks and fixture scenarios still require execution on a disposable local runtime before deployment approval.

## Existing schema compatibility

`CREATE TABLE IF NOT EXISTS` does not install foreign keys, a primary key, or uniqueness on an existing table. `CREATE INDEX IF NOT EXISTS` can also accept the name of an unrelated or incorrectly shaped index. The migration now inspects PostgreSQL catalogs and raises SQLSTATE `23514` for missing/incompatible notification columns, keys, validated foreign keys, event uniqueness, or expected indexes. Provenance columns must have the expected types and NOT NULL requirements. Equivalent constraint names are accepted; foreign keys must retain NO ACTION update/delete behavior.

A compatible prototype may lack `is_active`; that column and its default are added. A prototype missing constraints is refused and the current file's transaction rolls back, preserving records. Inspect duplicates, orphans, incompatible types, and existing grants; repair them only through a separately reviewed additive change. Do not silently discard duplicate events or orphan rows. Files commit separately: if 002 fails, a successful 001 remains applied and can be rerun after remediation.

## Opt-in disposable local PostgreSQL validation

The validator never imports app configuration or reads `DATABASE_URL`. It uses only `PHARMAONE_MIGRATION_TEST_URL` and requires `PHARMAONE_RUN_LOCAL_PG_MIGRATIONS=1`. The URL must use `postgresql` or `postgresql+psycopg`, an explicit user, literal `127.0.0.1` or `[::1]`, no query parameters, and a database named `pharmaone_migration_test_` plus 1–30 lowercase letters/digits/underscores. DNS names, Unix sockets, remote hosts, standard app database names, and URL connection overrides are rejected before connecting. Server address and database identity are checked again after connecting.

Use an already available **disposable local cluster**, never a tunnel or forwarded production database. Provision a dedicated maintenance database such as `pharmaone_migration_test_local` and a local role with CREATEDB beforehand. The validator does not start software or provision the maintenance database. Supply the test URL through a local secret mechanism without echoing credentials.

From `api`, after setting the separate test URL:

```powershell
$env:PHARMAONE_RUN_LOCAL_PG_MIGRATIONS = '1'
.\.venv\Scripts\python.exe migrations/validate_postgres.py
# Equivalent pytest entry point:
.\.venv\Scripts\python.exe -m pytest tests/test_postgres_migrations.py -q
```

Without opt-in, pytest runs target guard tests and reports the real PostgreSQL test as skipped. The CLI fails closed without opt-in. The validator requires the existing project dependencies (`psycopg`, SQLAlchemy); it does not download anything.

It creates seven randomly named `pharmaone_migration_test_*` databases from `template0`. Each receives synthetic pharmacy, inventory, regulatory alert, match, investigation, and ingestion run records. It applies both files twice, checks retained fields and provenance defaults, exercises primary key/foreign key/unique/NOT NULL enforcement, and checks index definitions, RLS, client-role ACLs, PUBLIC ACLs, and fixture-owner DML access. It seeds permissive fixture default privileges before migration so grant checks actually exercise revocation. Compatible prototypes retain notification state. Prototypes missing a primary key, foreign key, uniqueness, or having an incorrect index or provenance type must fail transactionally.

**No database, schema, table, or record is dropped, truncated, or reset.** Fixture databases are retained for review. A repeat validation creates a fresh set. Successful output lists their names. If a check fails, inspect only the generated `pharmaone_migration_test_*` databases in the disposable cluster. No roles are created or modified. Existing `anon`/`authenticated` roles are tested when present; absent roles are listed in the result and their behavior remains unverified. A cluster with these roles present is needed to exercise both client-role checks. Synthetic fixtures include the relationship columns relevant to the migrations; they are not a clone of the full production schema.

## Deployment role and schema readiness

Before an approved deployment:

1. Confirm the intended PostgreSQL instance, take the normal managed backup, and run the disposable local validation above successfully. Then review differences in the intended deployment schema without mutating it.
2. Confirm `public.pharmacies(id)`, `public.inventory_items(id)`, `public.regulatory_alerts(fingerprint)`, and `public.ingestion_runs` already exist. Referenced columns must be primary/unique keys. Review retained row counts and existing notification duplicates/orphans. Neither file creates the baseline application schema.
3. Use an approved migration role with schema USAGE/CREATE, ownership of an existing notification table and `ingestion_runs` (or an authorized owning role membership), and REFERENCES privileges on parent keys. ALTER TABLE, RLS, and REVOKE require ownership or equivalent administrator capability. Do not run DDL from API startup.
4. Apply 001 then 002. Inspect `pg_constraint`/`pg_index` for validated keys and ready/valid expected indexes; inspect `pg_class.relrowsecurity`, `pg_policies`, `relacl`, and `has_table_privilege` for all client DML privileges. Direct revokes do not remove privileges inherited through other role memberships; those memberships require separate review.
5. Check the actual API database role separately. RLS is enabled with no new policies. Owners bypass ordinary RLS unless FORCE ROW LEVEL SECURITY is set; a distinct role needs explicit table DML grants **and** an approved RLS strategy (appropriate policies or a deliberately authorized BYPASSRLS server role). Grants alone do not bypass RLS. These migrations grant no new API role privileges and do not prove that a deployment role can write. Never grant browser `anon`/`authenticated` direct table access to make API writes succeed.
6. Run the approved API smoke checks under the actual server role and record identifiers/change window. Existing startup checks currently verify columns/table presence only; they do not validate constraints, index definitions, role grants, or RLS runtime behavior. This pair only changes notification security; it does not establish RLS/grants for all other app tables.

Readiness is incomplete until the actual local PostgreSQL scenarios and deployment-role checks pass. No production connection or deployment is authorized by this validator.

## SQLite differences

Local SQLite startup uses `Base.metadata.create_all()` plus additive column/index repair. PostgreSQL startup checks expected table/columns and deliberately does not create schema or change grants. SQLite has no PostgreSQL roles, table grants, RLS, TIMESTAMPTZ catalog contract, or JSON type validation. SQLite foreign key enforcement depends on `PRAGMA foreign_keys`; adding fields/indexes to an existing SQLite table does not add omitted foreign keys or uniqueness. Local SQLite success must not substitute for PostgreSQL migration execution or security verification.

## Rollback

The default rollback restores the prior application version while retaining additive tables, columns, and notification/provenance records. Do not automatically reverse security revocations or disable RLS. A failed SQL file rolls back its own transaction; inspect whether the earlier file already committed before resuming.

Do not drop the table/columns as an automatic rollback. Any later removal requires an export and verification of affected records, confirmation that all application versions have stopped referencing them, and explicit database-owner approval for a separately reviewed removal. Fixture cleanup is likewise a separate operator action within the disposable cluster; the validator performs none.
