# PharmaOne AI

PharmaOne is a prototype that joins public CDSCO Not of Standard Quality (NSQ) records to pharmacy batch inventory and routes possible matches to pharmacist review. An NSQ finding is not automatically a recall, and the app never blocks dispensing.

## Current local evidence

The workspace demo uses the verified historical TinyFish snapshot in `evidence/cdsco-aug-2026-tinyfish.json`. Its reporting period is **AUG-2026**. The local SQLite database currently contains five regulatory records, three synthetic inventory rows, two potential matches, and two notification records. Both notifications are already acknowledged. No live source check is recorded; this is historical playback, not continuous monitoring.

No production deployment, production database, or paid TinyFish/Sarvam call was used in this work. Do not run the operator ingestion command for the offline demo.

## Start locally

The API is configured for the workspace SQLite database. From PowerShell:

```powershell
Set-Location 'D:\PharmaOne - Copy\api'
$env:PHARMAONE_ENV = 'local'
$env:DATABASE_URL = 'sqlite:///./pharmaone_development.db'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In a second terminal:

```powershell
Set-Location 'D:\PharmaOne - Copy\web'
npm.cmd run dev
```

Open [http://localhost:3000](http://localhost:3000). The API docs are at [http://localhost:8000/docs](http://localhost:8000/docs). The existing Supabase Auth integration needs a suitable test project/account; use only an approved test identity. Keep provider and database secrets in ignored server-side environment files. Never place a service-role key, TinyFish key, or Sarvam key in a `NEXT_PUBLIC_*` variable.

Before any database command, set both local environment variables above and verify the resolved engine is SQLite and the database file is inside this workspace. The application uses PostgreSQL in production, but no PostgreSQL or production database was touched here.

## Demo and verification

- [Four-minute demo and architecture](docs/HACKATHON_DEMO.md)
- [Matching evaluation](docs/matching-evaluation.md)
- [Database migration plan](api/migrations/README.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Deployment readiness](docs/DEPLOYMENT_READINESS.md)
- [Current verification report](docs/FINAL_VERIFICATION_REPORT.md)

Run the API tests from `api/` with the explicit SQLite environment. Frontend checks from `web/` are `npx.cmd tsc --noEmit`, `npm.cmd run build`, and `npm.cmd test -- --workers=1`. PostgreSQL integration tests require a separately configured isolated database and were skipped here.

TinyFish retrieval is an operator-controlled, bounded operation. The offline demo needs no provider call. MiniLM is optional, local-cache-only, and candidate-retrieval evidence cannot confirm a match. Match explanations require exact batch evidence and conservative product/manufacturer/strength checks; ambiguous cases go to verification.
