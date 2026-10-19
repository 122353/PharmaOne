# Local demo and manual acceptance checklist

Use the [current README](../README.md) and [four-minute demo](HACKATHON_DEMO.md). Keep the demo offline, set `PHARMAONE_ENV=local` and `DATABASE_URL=sqlite:///./pharmaone_development.db`, and confirm the resolved engine and path before any database command.

## Current saved demo baseline

- Source panel says **Historical snapshot imported** for **AUG-2026** and reports no live source check.
- Local SQLite contains five regulatory records, three synthetic inventory rows, two potential matches, and two notifications. Both notifications are already acknowledged, so unread count is zero.
- Review links open the alert fingerprint and preserve the official source period. No match proves stock is safe, and an NSQ entry is not automatically a recall.
- The saved baseline has no strength-conflict match. Demonstrate the 300mg-versus-600mg safety case with the isolated regression/browser fixture below; it does not mutate the saved database.

## Local regression commands

From `api/`:

```powershell
$env:PHARMAONE_ENV = 'local'
$env:DATABASE_URL = 'sqlite:///./pharmaone_development.db'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest tests\test_verified_snapshot.py::test_verified_alert_to_synthetic_pharmacy_hold_persists_and_isolated -q
```

From `web/`:

```powershell
npx.cmd tsc --noEmit
npm.cmd run build
npm.cmd test
```

The full local suite currently passes with 137 backend passes and 12 browser passes. Three PostgreSQL-only backend cases are skipped because no isolated PostgreSQL test server is configured.

## Manual acceptance not performed here

- Real Supabase signup/reset email delivery and two-account browser isolation.
- Live TinyFish, Sarvam chat/OCR/translation, or any paid provider call.
- Physical phone camera or printed medicine label.
- PostgreSQL migration execution, Docker runtime, production deployment parity, backups/restore, or hosted monitoring.

Any production Supabase change, hosted PostgreSQL migration, paid provider call, or deployment requires explicit user approval. Do not use production data to complete this checklist.
