# Deployment readiness and recovery

**Status: local deployment verified; public production deployment not approved or tested.** The Docker Compose file parses, but Docker Desktop's Linux engine was unavailable during verification. The tested path is the two-terminal local startup in [README](../README.md).

## Before a public deployment

1. Use the existing Supabase Free PostgreSQL project through its IPv4 compatible session pooler and HTTPS hostnames for web and API. Only the Supabase project URL, publishable key and public API URL may be exposed as `NEXT_PUBLIC_*` build variables. Never put the Supabase service-role key in the browser.
2. Use the reviewed [Render blueprint](../render.yaml) on the Free plan with one worker. Set `DATABASE_URL`, `SUPABASE_URL` and exact HTTPS `ALLOWED_ORIGINS` in Render secret prompts; `PHARMAONE_ENV=production` rejects SQLite and insecure origins. Set `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` in Vercel for Production and Preview. Do not configure paid TinyFish or Sarvam keys in the hosted service under the ₹0 budget. Cached CDSCO evidence remains visible with its retrieval timestamp.
3. Configure Supabase Authentication URL allowlists and verified custom SMTP using [email setup](SUPABASE_EMAIL_SETUP.md). Test signup confirmation, password reset, logout and a second confirmed account before opening registration.
4. Verify the providers' HTTPS ingress and upload limits; the API limits CSVs to 2 MB and optional images to 5 MB. Use `/health` on the API. Access logs are disabled in the Render start command. Do not log authorization headers or request bodies.
5. Install `api/requirements-dev.txt` locally and run `python -m pytest tests -q`, the opt-in PostgreSQL suite, `npx tsc --noEmit`, `npm run build`, `npm test`, `python scripts/check_secret_leaks.py`, and `docker compose --env-file web/.env.local config -q` before release. Confirm no local `.env` files or provider keys enter an image or repository.
6. Establish a versioned migration and backup process before applying schema changes to a production database. Current startup uses SQLAlchemy `create_all` and RLS/grant setup; it does **not** safely migrate existing columns. Do not treat successful startup as migration verification.
7. Render Free has 512 MB RAM and can sleep after inactivity; Vercel Hobby is restricted to personal, non-commercial use. Confirm account billing settings before provisioning. Do not add a payment method or enable overage billing. Paid TinyFish/Sarvam operations stay local and manual under separate authorization.

## Backup and restore exercise

Use the managed database provider's encrypted, scheduled backups and record retention period. Before any production migration, take a fresh backup and verify that a staging restore contains expected row counts and tenant/RLS policies. For a self-hosted PostgreSQL instance, `pg_dump -Fc` and `pg_restore` are suitable tools, but use credentials supplied by the deployment secret manager and a private backup destination; never commit dumps or paste connection strings into chat. Exercise restoration with synthetic records, not by overwriting the live database.

## Secret rotation

Rotate keys in the provider dashboards or deployment secret manager during a planned maintenance window. Update backend secrets, restart the API, perform one health and authorized read test, then revoke the old key. Rotate Supabase JWT signing keys only with a tested overlap procedure so current sessions are not unexpectedly invalidated. Do not print old or new keys in logs or tickets.

## Local Docker smoke test when the engine is available

From `D:\PharmaOne`, run `docker compose --env-file web/.env.local up --build`, check `docker compose ps`, open `http://localhost:3000/`, and check `http://localhost:8000/health`. The Compose stack uses a fresh local PostgreSQL volume; it does not automatically contain the prior Supabase TinyFish records. Do not claim the CDSCO workflow is live in the container until official records are imported or a separately approved sync is run.
