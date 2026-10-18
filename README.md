# PharmaOne AI

PharmaOne reviews CDSCO NSQ records against pharmacy batch inventory. It uses Supabase Auth, FastAPI, PostgreSQL, a centrally managed TinyFish retrieval command, browser Tesseract.js OCR, small locally trained advisory models, and optional Sarvam chat, OCR, and translation. Matches require pharmacist review. A simulated hold never restricts real stock.

## Local startup

From `D:\PharmaOne`, configure ignored environment files if they do not exist:

```powershell
cd D:\PharmaOne
python scripts\configure_local.py
```

Set the PostgreSQL connection and Supabase project URL in `api/.env`. Set the Supabase project URL and publishable/anon key in `web/.env.local`. The Supabase project must use asymmetric JWT signing. Keep `TINYFISH_API_KEY` and `SARVAM_API_KEY` only in `api/.env`. Both provider keys are configured locally. The central TinyFish sync completed one approved `AUG-2026` run; ten stored rows were compared against the official CDSCO database. One separately approved live Sarvam chat response passed ContextOS evidence checks and persisted a success audit. Never commit either env file. Existing local env files are not overwritten by the helper.

Run the API:

```powershell
cd D:\PharmaOne\api
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

In a second terminal, run the web app:

```powershell
cd D:\PharmaOne\web
npm ci
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). API documentation is at [http://localhost:8000/docs](http://localhost:8000/docs). The configured database retains the prior verified snapshot and ten records from the completed central `AUG-2026` sync. Synthetic pharmacy inventory can be uploaded through CSV or imported from the clearly labeled mock ERP adapter.

## Central source and AI operations

Ordinary pharmacy accounts cannot set TinyFish keys or start provider syncs. With separate approval for the paid operation, an operator can run a bounded single-period sync:

```powershell
cd D:\PharmaOne\api
python -m app.ingest_service AUG-2026 --limit 10
```

The command validates source rows, stores provenance and meaningful versions, rematches pharmacy inventory, logs run status, and refuses overlapping PostgreSQL runs. There is no scheduled national scrape. The key is not sent to the browser.

`SARVAM_API_KEY` is set only in the API environment. ContextOS returns an evidence-only explanation if the provider answer is incomplete, invalid, or fails regulatory checks. Live chat passed once for batch `VRNT-933`; OCR and translation have only mocked verification and need separate approval for live calls.

The scan page runs Tesseract.js in the browser and keeps images on the device. It shows raw OCR text, then requires manual correction before the API compares confirmed identifiers. The API runs PharmaMatch product similarity and PharmaClassify quality-category inference from versioned JSON artifacts in `api/model_artifacts`. Both were trained locally from synthetic examples by `python api/scripts/train_models.py`. Their predictions are advisory: exact normalized batch and conservative manufacturer checks control match status. PharmaClassify may return `unclassified`; its synthetic holdout was 6/10 and has not been clinically validated.

## Verification

```powershell
cd D:\PharmaOne\api
python -m pip install -r requirements-dev.txt
python -m pytest -q
$env:PHARMAONE_TEST_POSTGRES='1'; python -m pytest tests\test_postgres_security.py tests\test_postgres_workflow.py -q
cd D:\PharmaOne\web
npx tsc --noEmit
npm run build
npm test
```

The PostgreSQL tests use rollback protected synthetic records. Browser tests mock Supabase Auth and API responses; they do not prove live signup or paid provider calls. See the [current verification report](docs/FINAL_VERIFICATION_REPORT.md), [feature status](docs/FEATURE_STATUS.md), [manual checklist](docs/FINAL_TESTING_CHECKLIST.md), [email setup](docs/SUPABASE_EMAIL_SETUP.md), and [known limitations](docs/KNOWN_LIMITATIONS.md).

## Docker

`docker compose --env-file web/.env.local config` validates the configuration. When Docker Desktop's Linux engine is running:

```powershell
cd D:\PharmaOne
docker compose --env-file web/.env.local up --build
```

Docker runtime was unavailable during this verification. The local two-terminal startup above is the tested path. See [deployment readiness](docs/DEPLOYMENT_READINESS.md) for HTTPS, exact CORS origins, secret management, backups, spend limits, migration and restore requirements before any public release.

## ₹0 public hosting preparation

The checked-in [Render Free blueprint](render.yaml) and [Vercel build config](web/vercel.json) are ready for review. See the [public deployment checklist](docs/PUBLIC_DEPLOYMENT_CHECKLIST.md) and [readiness report](docs/PUBLIC_DEPLOYMENT_REPORT.md). No public deployment has been performed. The Git checkout has no remote, so GitHub push deployment first needs a new authorized repository. Keep paid TinyFish and Sarvam keys out of Render until a separate paid-call authorization; the previously retrieved CDSCO snapshot remains available from Supabase.
