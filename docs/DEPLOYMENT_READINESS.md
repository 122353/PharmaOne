# Deployment readiness and recovery

**Status: local prototype only. No deployment was requested or performed.** The production Vercel, Render, Supabase, and provider configurations remain unchanged. All code changes and database checks in this task stayed inside the local workspace; the active demo database is SQLite.

## Before any future deployment

1. Obtain explicit approval for the target environment and deployment window. Prepare an isolated staging project first; do not point local tests at production.
2. Review the deployment provider's current plan, memory, sleep, build, and billing limits. Do not enable overage billing or add a payment method without approval. Keep TinyFish/Sarvam calls disabled until a separate cost-bounded approval exists.
3. Set API environment to production only in the approved hosted service. Require PostgreSQL, HTTPS, and exact HTTPS CORS origins. Keep the Supabase service-role, JWT, database, TinyFish, and Sarvam credentials server-side; expose only the Supabase public key and API origin to the browser.
4. Configure authentication redirects and verified SMTP, then complete signup, reset-password, logout/login, and two-pharmacy isolation checks using test accounts.
5. Review and apply [the additive PostgreSQL migrations](../api/migrations/README.md) with a migration role after a backup. API startup checks that required PostgreSQL columns exist; it does not run `create_all()`, apply DDL, or change grants. The SQL migration has not been executed against PostgreSQL in this task.
6. Run the backend suite against SQLite and an isolated PostgreSQL database, TypeScript, production build, browser suite, dependency audits, and secret scans. Confirm environment files, SQLite DBs, logs, caches, and monitoring history remain ignored.
7. Test backup restoration, health monitoring, access/error logging, provider limits, and incident/key rotation procedures before serving real pharmacy inventory.

## Scheduling proposal

Do not run an in-process scheduler inside a sleeping web worker. If recurring retrieval is later approved, use a single one-shot scheduled job or operator-triggered command that:
- accepts one reporting period and enforces the existing row bound;
- uses a database lock to prevent overlap;
- checks an explicit spend ceiling and kill switch before calling TinyFish;
- stores sanitized run provenance and source status;
- deduplicates unchanged records and notifies only on new or materially changed evidence.

The proposed schedule is disabled. The current demo is offline and requires no paid provider call.

## Backup, rollback, and recovery

Use the managed PostgreSQL provider's encrypted backups only after a deployment is approved. Before a migration, take a fresh backup and verify a staging restore. Roll back application code while retaining the additive notification/provenance tables and rows; do not drop tables as an automatic rollback. See the migration guide for the safe data-preserving rollback procedure.

Rotate keys through the provider's secret manager during a planned window. Update server-side values, verify health and an authorized test read, then revoke the old key. Never paste credentials or connection strings into source files, tickets, or logs.

## Local Docker

Docker runtime was not exercised. A parsed Compose file would only validate static configuration, not prove the stack can start or that it contains the verified evidence snapshot. Use SQLite local startup for the current demo.
