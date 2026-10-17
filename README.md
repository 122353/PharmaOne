# PharmaOne AI

Source-backed CDSCO NSQ review for pharmacy batch inventory. The application is an MVP; it does not direct dispensing or implement a real stock hold.

## Status

- Backend API, PostgreSQL data model, Supabase JWT verification, CSV import, deterministic matching, investigation audit records, encrypted TinyFish BYOK, and TinyFish browser-agent adapter are implemented.
- Web landing, auth, onboarding, import, dashboard, alerts, detail, investigations, inventory correction and settings are implemented.
- One TinyFish connector run retrieved five real August 2026 CDSCO rows and an independent browser check matched all 30 compared fields. Its verified snapshot is in `evidence/` and was imported into the current ignored local SQLite database. The app's own per-user BYOK sync endpoint still awaits a configured account and live verification; no source records are silently fabricated.
- Supabase Auth and a PostgreSQL service must be configured to exercise the complete signed-in flow. The current local integration tests use SQLite; PostgreSQL behavior has not yet been verified because the local Docker daemon was unavailable.

For the current verification status, secure beginner setup, and a short hackathon walkthrough, see [MVP verification](docs/MVP_VERIFICATION.md). Use `python scripts/configure_local.py` to create ignored local Supabase and PostgreSQL settings without printing credentials.

## Local run

1. Create a Supabase project. Configure email/password Auth. Use its project URL and **anon/publishable** key only in the web configuration. Supabase must issue asymmetric JWTs exposed through its JWKS endpoint.
2. Copy `.env.example` to `.env` at the repository root. Set `SUPABASE_URL`, database credentials, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `TINYFISH_ENCRYPTION_KEY`. Generate the encryption key with `python -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`. Never commit `.env`.
3. Start the full stack:

```powershell
cd D:\PharmaOne
docker compose up --build
```

Open `http://localhost:3000`. API docs are at `http://localhost:8000/docs`. Sign up, create your pharmacy profile, upload a CSV, then connect your TinyFish key in Settings. Click **Sync CDSCO with my account** only when you intend to spend that account's TinyFish credits.

For separate development servers:

```powershell
cd D:\PharmaOne
docker compose up -d db
cd D:\PharmaOne\api
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd D:\PharmaOne\web
Copy-Item ..\.env.example .env.local
npm ci
npm run dev
```

Set `DATABASE_URL` in `api/.env` if using separate dev servers. The root `.env` is loaded by Docker Compose; `web/.env.local` is read by Next.js. `NEXT_PUBLIC_API_URL` must be reachable in the user's browser.

## Verification

```powershell
cd D:\PharmaOne\api
python -m pytest tests -q
cd D:\PharmaOne\web
npm run build
npm run e2e
```

The browser test covers the public landing page without external credentials. One external TinyFish connector retrieval has been verified against CDSCO; full signed-in browsing, the app's own BYOK retrieval path, and PostgreSQL deployment still need configured services.

## Data and safety

The parser allows UTF-8 CSV up to 2 MB and 5,000 rows. It validates columns, quantity, ISO expiry dates and spreadsheet formulas. Missing critical identifiers remain in `Needs verification`. Matching uses conservative normalized product/manufacturer selection and exact batch comparison after case/whitespace normalization. A potential match is a review prompt. `No identified match` does not prove safety. NSQ does not automatically mean recall.

The TinyFish adapter requests a selected CDSCO reporting period and at most 25 records per run. Each stored row must carry that period. It stores source URL, period, retrieval timestamp, run provenance and observed revisions. It never starts automatically. The current adapter is synchronous and checks one period at a time; scheduled nationwide coverage and full pagination are not implemented. Provider failures leave previously retrieved records dated and visible.

An operator can run central ingestion with a separately funded service key: from `api`, run `python -m app.ingest_service AUG-2026 --limit 10`. Schedule that command only after choosing a budget and coverage policy. User-initiated jobs never select the service key.

Private data queries are owner scoped. TinyFish keys are encrypted with AES-GCM using `TINYFISH_ENCRYPTION_KEY`, separate from the database, and are never returned by the API. The service key is reserved for future administrative ingestion and cannot be selected from user accounts. In production, use HTTPS, a managed PostgreSQL backup policy, a stable encryption key from a secret manager, restricted CORS, and asymmetric Supabase JWT signing.

## Deployment

The Dockerfiles and Compose file are deployable to a host with Docker. Provide HTTPS reverse proxy and durable PostgreSQL storage. Set `ALLOWED_ORIGINS` to the exact web origin and build `NEXT_PUBLIC_API_URL` for the public API origin. Set Supabase email redirect URLs to the deployed web origin. The API creates tables on startup; use managed migrations before evolving the schema in a running installation. Do not expose the database port publicly on production hosts.
