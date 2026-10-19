# PharmaOne AI

**From Government Alerts to Pharmacy Action**

PharmaOne is an India-first pharmacy safety prototype that connects public CDSCO Not of Standard Quality (NSQ) records with a pharmacy's own batch-wise inventory. It helps a pharmacist identify which regulatory records may be relevant to their stock, review the evidence, and record a human decision.

> **Safety rule:** an NSQ record is not automatically a recall. PharmaOne never treats a regulatory quality finding as an automatic stop-sale instruction, and a missing match does not prove that stock is safe.

## Live prototype

- Frontend: https://pharma-one-six.vercel.app
- Backend health: https://pharmaone-api.onrender.com/health
- Source: CDSCO public NSQ database
- TinyFish: used for bounded browser-agent retrieval from the interactive CDSCO portal
- Sarvam AI: integrated for multilingual OCR/translation when configured

## What the prototype does

1. A pharmacist creates a pharmacy workspace.
2. Batch-wise inventory is uploaded from CSV.
3. TinyFish retrieves structured CDSCO NSQ records from the public interactive portal.
4. PharmaOne normalizes and stores source provenance.
5. The matching engine compares product, batch, manufacturer, strength and formulation.
6. Exact or plausible candidates are routed to a human review queue.
7. Notifications are created for relevant regulatory changes.
8. The pharmacist can inspect the CDSCO source, record an investigation and perform physical verification.
9. The Scan Medicine flow can read a package image with Sarvam AI OCR and falls back to on-device OCR if the provider is unavailable.
10. Regulatory findings can be translated into supported Indian languages for review.

## Architecture

```text
CDSCO public NSQ portal
        |
        v
TinyFish browser-agent retrieval
        |
        v
FastAPI ingestion + provenance
        |
        v
PostgreSQL / SQLite
        |
        +--> deterministic matching
        +--> PharmaMatch advisory similarity
        +--> PharmaClassify advisory category
        +--> optional MiniLM candidate retrieval
        |
        v
Notifications + pharmacist review
        |
        v
Next.js dashboard
        |
        +--> Supabase Auth
        +--> Sarvam OCR / translation
        +--> browser OCR fallback
```

## Tech stack

### Frontend

- Next.js 16
- React 19
- TypeScript
- Supabase Auth
- ZXing for QR/barcode reading
- Tesseract.js for browser OCR fallback
- Vercel deployment

### Backend

- FastAPI
- SQLAlchemy
- PostgreSQL in production
- SQLite for local/demo workflows
- Pydantic settings and validation
- Render deployment

### AI / ML / data integrations

- **TinyFish** - browser-agent retrieval of CDSCO NSQ records from the dynamic public portal
- **PharmaMatch** - advisory product-name similarity
- **PharmaClassify** - advisory classification of CDSCO findings
- **MiniLM** - optional semantic candidate retrieval; never used to confirm a match by itself
- **Sarvam AI** - multilingual document OCR, translation and contextual assistance

## Matching philosophy

The matcher is deliberately conservative.

- Exact batch evidence is treated as the strongest identifier.
- Product and manufacturer alignment are explained separately.
- Strength/formulation conflicts route the record to verification.
- Semantic similarity can suggest candidates, but it cannot override deterministic safety rules.
- All final decisions remain with the pharmacist.

Typical outcomes:

- `potential_match`
- `needs_verification`
- no identified match

## TinyFish retrieval

The CDSCO NSQ portal is interactive and the result table is loaded after filters are applied. PharmaOne uses TinyFish to operate that public interface and return structured rows.

The adapter accepts either an explicit reporting period such as `AUG-2026` or `LATEST`. Even when `LATEST` is used to select the source view, every stored record must carry the explicit reporting period returned by CDSCO for traceable provenance.

Provider usage is intentionally bounded:

- maximum configured provider requests per sync
- maximum record count per sync
- concurrency lock
- ingestion provenance
- deduplication
- no public unauthenticated trigger

## Scheduled monitoring

The repository includes `.github/workflows/regulatory-sync.yml`.

The scheduled job is fail-safe:

- if production secrets are configured, it performs one bounded latest-period sync
- if secrets are not configured, it exits cleanly without making a provider call

Required GitHub repository secrets:

- `PHARMAONE_DATABASE_URL`
- `PHARMAONE_SUPABASE_URL`
- `TINYFISH_API_KEY`

## Sarvam AI and OCR

The Scan Medicine flow first attempts the authenticated backend OCR route:

```text
image -> PharmaOne API -> Sarvam Document AI -> extracted fields -> pharmacist confirmation
```

If Sarvam is unavailable, the frontend falls back to on-device OCR.

The pharmacist must still confirm extracted medicine identifiers before matching against CDSCO records.

The alert-review interface also supports multilingual translation through Sarvam when `SARVAM_API_KEY` is configured on the backend.

## Local development

### 1. Clone

```bash
git clone https://github.com/122353/PharmaOne.git
cd PharmaOne
```

### 2. Configure environment

Copy `.env.example` and provide local values. Never place TinyFish, Sarvam, database passwords or service-role credentials in `NEXT_PUBLIC_*` variables.

Important backend variables:

```text
PHARMAONE_ENV
DATABASE_URL
DB_SSLMODE
SUPABASE_URL
SUPABASE_JWT_AUDIENCE
ALLOWED_ORIGINS
TINYFISH_API_KEY
SARVAM_API_KEY
```

Frontend public variables:

```text
NEXT_PUBLIC_API_URL
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
```

### 3. Initialize PostgreSQL when needed

For a fresh PostgreSQL database, run the checked-in migrations once before starting the API:

```bash
cd api
python -m app.migrate
```

The migration runner applies `000_base_schema.sql`, `001_monitoring_notifications.sql`, and `002_ingestion_run_provenance.sql` in order and records completed files in `schema_migrations`.

For local Docker Compose, this migration step is run automatically before the API process starts. `DB_SSLMODE=auto` disables SSL for localhost/`db` and defaults remote PostgreSQL connections to `require`. A provider-supplied `sslmode` query parameter takes precedence.

### 4. Start backend

```bash
cd api
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### 5. Start frontend

```bash
cd web
npm ci
npm run dev
```

Frontend: http://localhost:3000

## Repository layout

```text
api/
  app/
    main.py               FastAPI routes and review workflows
    tinyfish.py           CDSCO browser-agent adapter
    ingest_service.py     bounded ingestion + provenance
    scheduled_ingest.py   scheduled sync policy
    matching.py           deterministic matcher
    ml.py                 PharmaMatch / PharmaClassify helpers
    semantic_matching.py  optional semantic candidate retrieval
    sarvam.py             Sarvam client
    scan.py               OCR + scan matching routes
    notification_service.py
  tests/
  migrations/
    000_base_schema.sql
    001_monitoring_notifications.sql
    002_ingestion_run_provenance.sql

web/
  app/
    dashboard/
    alerts/
    inventory/
    scan/
    investigations/
    contextos/
  components/
  lib/

evidence/
docs/
.github/workflows/
```

## Verification and project docs

- [Hackathon demo and architecture](docs/HACKATHON_DEMO.md)
- [Matching evaluation](docs/matching-evaluation.md)
- [PostgreSQL migration notes](api/migrations/README.md)
- [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Deployment readiness](docs/DEPLOYMENT_READINESS.md)
- [Final verification report](docs/FINAL_VERIFICATION_REPORT.md)

## Current status

Implemented:

- public frontend
- deployed FastAPI backend
- Supabase authentication
- pharmacy onboarding
- CSV inventory
- CDSCO alert storage and provenance
- deterministic matching
- PharmaMatch / PharmaClassify
- optional MiniLM advisory retrieval
- notifications
- investigations and physical verification
- simulated hold workflow
- TinyFish live CDSCO retrieval
- latest-period retrieval logic
- Sarvam OCR integration
- multilingual alert translation
- QR/barcode scanning
- browser OCR fallback
- bounded scheduled-sync workflow

Repository portability fixes now included:

- reproducible base PostgreSQL schema migration
- explicit idempotent migration runner
- standard `postgres://` / `postgresql://` URL normalization
- local-vs-cloud PostgreSQL SSL handling
- Docker image copies model artifacts and migrations
- Docker Compose initializes a clean PostgreSQL volume before API startup
- Vercel helper configures `NEXT_PUBLIC_API_URL` with Supabase public variables
- API Docker build context excludes local secrets and virtual environments

Still requiring production acceptance/configuration rather than new core development:

- first successful scheduled production sync with repository secrets configured
- one live Sarvam OCR/translation smoke test with a non-sensitive sample
- one final signed-in end-to-end production walkthrough

## Responsible-use notes

PharmaOne is a pharmacist-assistance prototype. It does not diagnose patients, declare medicines dangerous, convert every NSQ finding into a recall, or automatically restrict dispensing. Official regulatory records and applicable instructions remain the authoritative source.

## License

No open-source license has been added yet. Until one is selected, the repository is publicly viewable but normal copyright rules apply.
