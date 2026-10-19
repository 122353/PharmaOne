# PharmaOne production deployment runbook

This is an approval-gated runbook. It records the sequence to use after a named owner approves a production change. No step in this document has been executed against Render, Vercel, Supabase, or a hosted database.

## Readiness

| Area | Status | Evidence or condition |
|---|---|---|
| Local SQLite workflow | TESTED | Local development database and database-only backend checks passed. |
| PostgreSQL migration harness | PARTIALLY TESTED | Guards and disposable-database tests pass; an actual PostgreSQL runtime is still required. |
| PostgreSQL migration execution | BLOCKED | Docker's Linux engine and local PostgreSQL binaries were unavailable during verification. |
| Render and Vercel configuration changes | NOT IMPLEMENTED | No cloud configuration, deployment, or traffic change was made. |
| Scheduled live ingestion | NOT IMPLEMENTED | The one-shot job is disabled by default and no live provider request was made. |

## Approval gate

Obtain written approval that identifies the target Render service, Vercel project, Supabase project, change window, responsible operator, database backup owner, and rollback owner. Confirm that a TinyFish call is approved separately before enabling a live source check.

Do not use the local development SQLite file as a production input. Do not copy secrets from local environment files into chat, source control, browser code, or deployment logs.

## Preflight

1. Confirm the repository revision has passed the approved review process and that `render.yaml` still uses `api` as its root directory, `pip install --no-cache-dir -r requirements.txt` as the build command, the documented Uvicorn start command, and `/health` as the health check.
2. Review Render's `autoDeployTrigger: commit`. A pushed commit can initiate a deployment. Disable or govern automatic deployment before pushing an unapproved revision.
3. Create and verify the provider's normal PostgreSQL backup and restore procedure. Record the backup identifier outside this repository.
4. Confirm the API's production database role, schema owner, RLS posture, grants, and connection pooler settings. The browser `anon` and `authenticated` roles must not receive direct DML access to application tables.
5. Confirm the frontend uses only public values. The server-side provider key remains API-only.

## Required environment names

Set values through the deployment providers' secret stores, never in source files.

### API service

`render.yaml` currently declares these API variables:

- `PYTHON_VERSION`
- `PHARMAONE_ENV` set to `production`
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_JWT_AUDIENCE`
- `ALLOWED_ORIGINS`

Set `ALLOWED_ORIGINS` to the exact HTTPS frontend origins. Do not use wildcard origins. The JWT issuer derives from the configured Supabase URL and the API accepts only validated asymmetric Supabase tokens with the configured audience and authenticated role.

Keep these scheduler variables absent or explicitly conservative until their approval gate is complete:

- `PHARMAONE_SCHEDULE_ENABLED=false`
- `PHARMAONE_SCHEDULE_MAX_REQUESTS`
- `PHARMAONE_SCHEDULE_MAX_RECORDS`
- `PHARMAONE_SCHEDULE_INTERVAL_HOURS`
- `PHARMAONE_SCHEDULE_PERIOD`
- `TINYFISH_API_KEY`

When the scheduler is enabled later, its code permits only one or two provider requests, one through 25 records, and an interval from six through 168 hours. A failed attempt consumes the same frequency budget. There is no API route or background loop that starts it.

### Frontend

Set these public Vercel variables to production HTTPS endpoints:

- `NEXT_PUBLIC_API_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

No service-role credential belongs in the frontend environment.

## PostgreSQL migration procedure

1. Before a hosted change, run `api/migrations/validate_postgres.py` against an already available disposable local PostgreSQL cluster. It needs explicit `PHARMAONE_RUN_LOCAL_PG_MIGRATIONS=1` and a separately supplied `PHARMAONE_MIGRATION_TEST_URL` that points to a loopback database named `pharmaone_migration_test_*`.
2. Review the generated fixture database names and test result. The validator creates seven retained disposable databases and does not drop, truncate, or reset any database.
3. In the approved change window, inspect the intended database for the baseline parent tables, duplicate notification events, orphan references, existing RLS policies, existing table privileges, and a migration role with the documented ownership and `REFERENCES` privileges.
4. Apply `api/migrations/001_monitoring_notifications.sql`, then `api/migrations/002_ingestion_run_provenance.sql`, with the approved migration role.
5. Inspect PostgreSQL catalogs for the notification primary key, three validated foreign keys, event uniqueness, expected indexes, RLS, and revoked client-role privileges. Inspect the provenance column types and NOT NULL constraints.
6. Start the API only after the migration checks pass. PostgreSQL API startup verifies required tables and columns; it does not create schema, validate constraints, validate grants, or prove RLS behavior.
7. Run the approved server-role smoke checks. Record only result identifiers and timestamps, not credentials or tokens.

Each migration file has its own transaction. A file that fails rolls back its own transaction. If the second file fails after the first committed, repair the documented incompatibility and rerun the second file. Rollback means returning the application to the prior compatible version while retaining additive data; do not drop notification or provenance data automatically.

## Deployment sequence

1. Deploy the API revision to a non-production environment with the target configuration and PostgreSQL schema.
2. Check `/health`, an unauthenticated API response, a verified-token response, exact-origin CORS behavior, owner scoping, a CSV validation error, and the notification list. Use synthetic records and remove them only through the approved test-data procedure.
3. Deploy the frontend with the production API URL and public Supabase values. Confirm that the browser has no server-side credentials and that failed API calls show safe errors.
4. Promote the API and frontend only inside the approved window. Keep scheduled ingestion disabled.
5. Review Render logs, provider resource usage, error rate, database connection saturation, and notification delivery state during the agreed observation period.

## Optional scheduler activation

After separate provider-budget approval, create a single external scheduler entry that invokes:

```text
python -m app.scheduled_ingest
```

Use the API service environment with the bounded scheduler variables. Do not create an HTTP trigger. If a Render Cron Job is selected, configure its UTC schedule, budget, and failure notifications in the provider console. Confirm the first run's source kind, request count, record count, and sanitized status before scheduling another run.

The offline rehearsal remains available without a provider call:

```text
python -m app.scheduled_ingest --playback
```

It imports the verified historical snapshot into an in-memory database only.

## Post-deployment acceptance

- Confirm source freshness distinguishes an imported historical snapshot from a successful live source check.
- Confirm a strength, manufacturer, formulation, or batch conflict cannot become a `potential_match`.
- Confirm a notification is scoped to its pharmacy, acknowledgements persist, and an investigation retains its review history after recheck.
- Confirm rate limiting returns `429` and `Retry-After` for bounded sensitive actions.
- Confirm attachments reject oversized or malformed inputs. The current validation is not malware scanning.

## Rollback and escalation

If application health or owner-scoped access fails, pause promotion, return the service to the last compatible application revision, and retain the backup and migration evidence for review. Do not disable RLS, grant browser roles table access, reset production data, or rerun paid ingestion to diagnose a deployment issue.

Escalate migration incompatibilities, RLS/grant failures, possible cross-tenant access, source provenance discrepancies, and unexpected provider spend to the designated database or security owner before proceeding.
