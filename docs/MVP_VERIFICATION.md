# MVP verification record

## Live source evidence

One TinyFish browser automation run used the connected TinyFish account to inspect the official [CDSCO NSQ database](https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug), select August 2026, and extract five rows. The [run record](https://agent.tinyfish.ai/runs/7d650bd4-71e6-49dc-b967-f95304ecb6aa) and [captured values](../evidence/cdsco-aug-2026-tinyfish.json) identify the source and provider run. An independent Playwright browser visit selected the same filters and compared product, manufacturer, batch, NSQ result, reporting source, and period for each row: **30 of 30 fields matched**. The [verification report](../evidence/cdsco-verification-report.json) includes the UTC check time and a SHA-256 digest of the exact captured snapshot. Rerun the comparison without another TinyFish charge:

```powershell
cd D:\PharmaOne\web
node scripts/verify-cdsco.mjs
```

The five verified rows were imported into the current ignored local SQLite database through `python -m app.verified_snapshot`. The command is idempotent, requires the matching verification report, and records the official source URL, TinyFish run ID, and database import timestamp. It does **not** exercise the PharmaOne BYOK sync endpoint. Once PostgreSQL is configured, run the same command from `D:\PharmaOne\api` to import this already verified snapshot without another provider call. A future fresh source sync requires an authenticated user to connect their own key in Settings.

An older local SQLite file was found with one missing provenance column. It was backed up as ignored `api/pharmaone.pre-verification.db` and repaired without deleting rows. Startup now repairs that specific legacy SQLite column; evolving a deployed PostgreSQL schema still needs managed migrations.

## Configuring Supabase locally

1. Create a project in the [Supabase dashboard](https://supabase.com/dashboard). Choose the free plan if offered. Save the database password in a password manager; do not paste it into chat.
2. In **Project Settings → JWT Signing Keys**, ensure an asymmetric ES256 key is **current/in use**, not only standby. For an existing legacy project, follow Supabase's [JWT signing keys guide](https://supabase.com/docs/guides/auth/signing-keys) to migrate and rotate. The backend verifies access tokens with the project's public JWKS.
3. In **Project Settings → API Keys**, copy the project URL and `sb_publishable_...` key. Never use the secret or service-role key in the web app. In **Connect**, copy the **Session pooler** PostgreSQL URI on port 5432 with `[YOUR-PASSWORD]` still in it. Supabase [documents the pooler](https://supabase.com/docs/guides/database/connecting-to-postgres) as the IPv4-compatible path.
4. In Supabase Auth URL configuration, set the site URL to `http://localhost:3000` and allow redirect URLs under `http://localhost:3000/**`. Keep email/password sign-in enabled. Confirm test accounts by email if confirmation is enabled.
5. In PowerShell, run the private setup helper. It prompts for the values, hides the publishable key and database password as you type, percent-encodes the password in the URI, generates a separate 32-byte encryption key, validates JWKS availability, and writes only ignored local files. It refuses to overwrite existing files.

```powershell
cd D:\PharmaOne
python scripts\configure_local.py
```

The helper creates `api/.env` and `web/.env.local`. Do not commit them. The hosted LLM key and TinyFish service key are optional and absent by design; the MVP's normalization and explanation paths are deterministic. Connect a personal TinyFish key only through the signed-in Settings page. Do not paste that key into chat or a `NEXT_PUBLIC_` variable.

## Local startup after configuration

In one PowerShell window:

```powershell
cd D:\PharmaOne\api
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

In a second window:

```powershell
cd D:\PharmaOne\web
npm ci
npm run dev
```

Open `http://localhost:3000`. If an older server is already using either port, stop that server first so the new environment files are loaded. API health is at `http://localhost:8000/health`. To load the verified records into the configured PostgreSQL database, run once from `D:\PharmaOne\api`:

```powershell
python -m app.verified_snapshot
```

## Verified and pending

The local test commands last returned **36 backend tests passed**, **3 public browser tests passed**, and a successful 15-route Next.js production build:

```powershell
cd D:\PharmaOne\api
python -m pytest tests -q
cd D:\PharmaOne\web
npm run e2e
npm run build
```

- **Verified:** One TinyFish retrieval returned five real August 2026 CDSCO NSQ rows; independent browser comparison matched 30 fields. The snapshot persists idempotently with run provenance in the current local SQLite database. An isolated API workflow test imports the verified alert, uploads clearly synthetic stock, creates an explainable potential match, records a simulated hold, reloads the investigation from a new client, and checks two-pharmacy isolation.
- **Verified in tests:** Missing manufacturer goes to verification, a wrong batch and different strength do not match, duplicate inventory is counted, keys are encrypted, another user cannot invoke a job with the owner's key, and invalid key validation does not echo the value. Public landing browser checks cover desktop, mobile width, and reduced motion.
- **Pending configuration:** Real Supabase sign-up and two-user browser journey, PostgreSQL persistence, and the app's own BYOK sync endpoint. The connector run does not establish that the BYOK endpoint works against the provider.
- **Pending environment:** Docker daemon and production container test. `docker compose --env-file .env.example config --no-env-resolution --quiet` validates the Compose syntax without starting containers. The independent local API/web startup above is the current alternative; both `http://localhost:3000/` and `http://localhost:8000/health` responded with HTTP 200 during this check, while an unauthenticated alerts request returned HTTP 401.

## Hackathon demonstration (about three minutes)

1. Sign up and name a **synthetic demonstration pharmacy**. State that no patient data is used.
2. Upload [`demo/synthetic-stock.csv`](../demo/synthetic-stock.csv). Show one exact Linezolid batch, a row missing its manufacturer, and rows with wrong batch or strength.
3. Open the August 2026 CDSCO alert for **Linezolid Tablets IP 600mg**, batch **TG261185**. Show the official source URL, reporting period, and retrieval time. Explain that the five displayed source rows came from the recorded TinyFish run and were independently checked.
4. On the dashboard, open the potential match. Point out the compared product, batch, and manufacturer evidence. The missing-manufacturer row remains a verification task.
5. Record an investigation and select **Simulated hold**. Refresh the page to show it persists. Explain that this is a pharmacist review record, not a real dispensing block or automatic recall declaration.

If demonstrating the snapshot import, call it a **verified prior TinyFish retrieval**, not a new live sync. Use the Settings sync button only when the personal key is connected and a new metered run is intended.
