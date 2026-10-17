# PharmaOne implementation plan

## Architecture

Next.js App Router serves the public and authenticated UI. Supabase Auth issues access tokens. FastAPI validates the token against the project's JWKS and owns all business data in PostgreSQL. A pharmacy belongs to its creator; every private query is filtered by that owner. TinyFish runs from the backend only, with either the requesting user's encrypted BYOK key or an explicitly configured service key. Public CDSCO records are shared and deduplicated; inventory and investigations are private.

## Milestones

- [x] 0. Schema, API contracts, configuration, and local/deployment instructions.
- [ ] 1. TinyFish browser retrieval adapter, strict extraction, provenance, deduplication, source health. Live run remains unverified without a key and paid-run approval.
- [x] 2. CSV validation, persistent inventory, deterministic explainable matching, tests.
- [ ] 3. Supabase session verification, pharmacy onboarding, ContextOS Lite, tenant tests. Code and tenant tests complete; real Supabase session test pending project credentials.
- [ ] 4. Landing, authentication, import, dashboard, alerts, investigation, settings UI. Build and public-page browser tests complete; signed-in browser journey pending Supabase.
- [ ] 5. Encrypted BYOK, simulated hold audit, end-to-end and build verification. Unit/integration tests complete; provider and PostgreSQL E2E pending configured services.

## Verification record

- `python -m pytest tests -q`: 26 passed on SQLite test database.
- `npm run build`: successful Next.js production build.
- `npm run e2e`: 2 public landing browser tests passed at desktop and 390 px.
- `npm audit --omit=dev --audit-level=moderate`: zero production dependency advisories.
- `GET /health`: 200 and `GET /api/me` without a token: 401 on a local FastAPI server.
- Docker daemon was unavailable, so container and PostgreSQL deployment were not exercised.
- No TinyFish or Supabase credentials were available. No metered TinyFish run was started.

## Safety decisions

NSQ is a quality classification, not a recall order. A potential match is a pharmacist review task. No match is not a safety conclusion. Holds are simulation records only. Live records are shown only after a successful TinyFish run. The app never starts metered TinyFish retrieval automatically during local development or dashboard loading.

## API contract

Authenticated routes: `GET /api/me`, `PUT /api/pharmacies/current`, `GET /api/pharmacies/current`, `POST /api/inventory/import`, `GET /api/inventory`, `PATCH /api/inventory/{id}`, `GET /api/alerts`, `GET /api/alerts/{id}`, `GET /api/matches`, `POST /api/matches/recheck`, `GET /api/investigations`, `POST /api/investigations`, `GET /api/ingestion/status`, `POST /api/ingestion/sync`, `GET|POST|DELETE /api/integrations/tinyfish`, `POST /api/integrations/tinyfish/test`, `GET /api/dashboard`. Every route returns JSON except CSV import. Errors use FastAPI's `detail` field.
