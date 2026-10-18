# PharmaOne final MVP verification — current status (18 October 2026)

## Verdict

**PARTIALLY VERIFIED — BLOCKERS REMAIN.** The local app is running and its core source-to-pharmacy path has live regulatory evidence, PostgreSQL persistence, deterministic matching, a prior approved live ContextOS response, and automated workflow coverage. External email delivery, real two-account acceptance, live OCR/translation, physical camera use and Docker runtime remain open.

## Live verified

- The previously approved central TinyFish run `c4f6314f-8d7d-4664-854d-053384dc042d` for `AUG-2026` succeeded and stored ten CDSCO NSQ records. A read-only comparison against the [official CDSCO public database](https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug) located all ten by exact period and batch: zero missing, zero substantive mismatches. Product, batch, finding, period and reporting source matched; manufacturer was byte-exact for eight and differed only in whitespace for two. All ten records retained the official table URL and a valid retrieval timestamp. See [full field-by-field evidence](../evidence/cdsco-live-compare-2026-10-18.json) and `scripts/verify_cdsco_snapshot.py`. CDSCO supplies a table URL, not a stable URL for each row: filter the database to `AUG-2026` and find the exact batch.
- One previously approved live Sarvam Chat 105B answer for `VRNT-933` passed the ContextOS handler and was persisted as a `success` audit with an official citation. This was a handler/database validation, not a signed-in browser acceptance. No new TinyFish, Sarvam OCR or Sarvam translation request was made in this final pass.
- The configured PostgreSQL database was exercised by three rollback-protected integration/security tests. Local API `/health` and web `/` both returned HTTP 200 after restart.

## Automated verified in this pass

- Backend: `python -m pytest tests -q` from `api` — **99 passed, 3 skipped, 1 Starlette deprecation warning**. The skipped tests are the opt-in PostgreSQL tests; run separately with `PHARMAONE_TEST_POSTGRES=1`, they gave **3 passed**. This includes owner scoping, import, matching, investigation idempotency, provider mocks, OCR error handling, attachment access and malformed upload rejection.
- Frontend: `npx tsc --noEmit` and `npm run build` passed; the build generated 21 routes. `npm test -- --reporter=line` gave **8 passed**, covering landing/mobile/reduced motion, QR and product-only barcode fixtures, a fully synthetic pharmacy journey, refresh persistence, ContextOS English/Hindi and an intercepted Supabase email-rate-limit response. Browser Auth/API workflow responses are mocked; this does not prove live login or live provider invocation.
- Docker Compose static configuration parsed with `docker compose --env-file web/.env.local config -q`. Health checks are present and published ports bind to localhost. `docker info` could not connect to Docker Desktop's Linux engine; no container startup was claimed.
- Final local smoke check: API `/health` returned `200`, unauthenticated `/api/me` returned `401`, web `/` returned `200`, and the response included `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY`. `git diff --check` and the local provider-key leak scan passed; both private env files are Git-ignored. No secret values were printed.

## Fixes and security findings

- Signup now blocks duplicate submissions, shows a pending state and safe rate-limit guidance. A reset-password callback page and explicit confirmation/recovery redirects are present. Permanent delivery is blocked until the user configures a verified custom SMTP sender in Supabase and tests real mail; see [steps](SUPABASE_EMAIL_SETUP.md). During development of the intercepted signup browser test, an initial route pattern missed Supabase's query-bearing URL and at least one synthetic signup attempt received a rate-limit response. The pattern was corrected; the passing test asserts one intercepted request. No account creation was verified from that attempt.
- Investigation review status, physical verification and simulated hold are represented separately. Repeated identical actions do not add audit events, browser buttons block double clicks, note/event state refreshes immediately, and historical records remain. The simulated hold never restricts stock.
- Private attachment endpoints retain pharmacy ownership checks and no-store downloads. Images are decoded; malformed PDFs without basic trailer markers, MIME mismatches and files over 2 MB are rejected. These checks do not constitute antivirus or complete PDF validation.
- Supabase JWT verification checks signature, issuer, audience and authenticated role. PostgreSQL application tables have RLS enabled and direct `anon`/`authenticated` grants revoked; the FastAPI owner-scoped routes are the data gateway. Secrets remain in ignored backend configuration, and provider calls are server-side. No client-side service key was added. Frontend security headers were added. Production readiness still needs HTTPS ingress, managed migrations/backups, monitoring, secret rotation planning and provider-wide budget alerts.

## Blocked or manual acceptance

- **SMTP and real Supabase auth:** no verified sending domain/custom SMTP delivery test. One prior user-reported signup exists, but this pass did not verify a fresh confirmation, password reset, logout/login cycle or two simultaneous real accounts.
- **Two pharmacies:** synthetic PostgreSQL isolation passed; a second confirmed Supabase identity and signed-in cross-account browser/API acceptance remain manual.
- **Sarvam OCR and translation:** adapters, validation and mocked tests pass, but account-specific model/endpoint behavior and output quality require one separately approved live call each. No paid test was initiated here.
- **Camera and Hindi:** synthetic QR/EAN decoding passed; physical camera permissions/device switching and a printed label require a phone. Navigation, auth, password recovery, dashboard and key scan/ContextOS strings persist in Hindi, but full legacy-page translation is incomplete.
- **Docker and production:** static Compose passes; Linux engine unavailable. Public deployment, live Auth settings changes and destructive migrations were not performed. The reference ERP and supplier graph remain explicitly synthetic; no commercial ERP or verified real-world supply chain is claimed.

Use the [manual acceptance checklist](FINAL_TESTING_CHECKLIST.md), [feature status](FEATURE_STATUS.md), [known limitations](KNOWN_LIMITATIONS.md), [deployment readiness guide](DEPLOYMENT_READINESS.md) and [four-minute demo](HACKATHON_DEMO.md) for the remaining steps. No new paid provider call is needed to inspect the existing ten-record source evidence.

---

## Historical pre-centralization report

The following section is retained as historical evidence. Its BYOK references and earlier test counts are obsolete; the status above is authoritative.

## Verdict

**PARTIALLY VERIFIED — BLOCKERS REMAIN.** The app is locally accessible and its deterministic pharmacy workflow passed against PostgreSQL and in a mocked signed-in browser. A live two-account Supabase browser run, the app's own TinyFish BYOK sync, and Docker startup have not been executed.

## Implemented and inspected

- Next.js landing, auth forms, pharmacy onboarding, CSV mapping/import, dashboard, alerts, inventory correction, investigation activity, simulated hold, and settings.
- FastAPI with asymmetric Supabase JWT verification, pharmacy-scoped private queries, PostgreSQL models, CSV validation, deterministic product/manufacturer comparison, exact normalized batch comparison, audit events, and AES-GCM encrypted per-user TinyFish keys.
- A bounded server-side TinyFish SSE adapter, source record normalization, deduplication, revisions, official source URL, retrieval time, and user-selected account enforcement.
- Five August 2026 CDSCO NSQ rows from a prior TinyFish connector run are in the configured PostgreSQL database. [Source verification evidence](../evidence/cdsco-verification-report.json) records 30 compared fields and zero mismatches on 17 October 2026. This is a verified **prior snapshot**, not a live PharmaOne BYOK run.
- NSQ findings, potential inventory matches, pharmacist review, and simulated holds are labeled separately. A simulated hold does not restrict dispensing.

## Bugs found and fixed in this pass

1. Duplicate rows within one CSV upload could cause a database uniqueness error when the production session had autoflush disabled. The import now counts them as duplicates before inserting. The API test fixture now uses the production autoflush setting.
2. Inventory edits accepted malformed expiry dates. The edit schema now validates ISO dates before updating.
3. The source status endpoint returned another user's latest TinyFish run state and error. It now includes only the caller's runs and shared central/snapshot runs.
4. Sync requests silently selected the user's TinyFish account if `account` was omitted. The caller must now explicitly select an account; service accounts remain forbidden to user API calls.
5. Compose required a missing root `.env` despite existing secure `api/.env` and `web/.env.local`. It now reads those files via `api.env_file` and `--env-file web/.env.local`.
6. The web Docker build context lacked a `.dockerignore`, so local environment files could be sent to Docker and copied into an image. They are now excluded. Compose mounts verified evidence read-only for optional snapshot import.

## Executed checks

- `PHARMAONE_TEST_POSTGRES=1 python -m pytest tests -q` from `api`: **48 passed**, one Starlette/TestClient deprecation warning. One test exercised the actual configured PostgreSQL connection with synthetic owner IDs, an overridden Auth dependency, and a mocked TinyFish response. Its outer transaction rolled back all test records. The other 47 tests used isolated SQLite or pure functions. CSV coverage includes empty/malformed/oversized files, row limits, Unicode, invalid dates, formulas, missing fields, and duplicates.
- PostgreSQL connection: `SELECT 1` returned 1. All nine expected tables were present; model columns matched live columns. Foreign keys and unique constraints were inspected. Prior to the test the database held five alerts, one pharmacy, one successful snapshot run, and zero TinyFish connections. The PostgreSQL test verified cross-session reads, investigation state and audit events, cross-pharmacy denial, and rollback cleanup.
- Supabase: public JWKS responded HTTP 200 with one signing key. An invalid synthetic password login returned HTTP 400, establishing Auth endpoint reachability only. Live API `/health` returned 200; `/api/me` returned 401 without a token and with an invalid token.
- Mocked TinyFish SSE parsing: the adapter sent the selected period and server-side key to the expected endpoint and parsed a COMPLETE event into a source-backed record. PostgreSQL workflow tested encrypted key storage, account selection, record persistence, matching, and simulated hold using a mocked provider response. **No paid provider call was made in this pass.**
- `npm run e2e`: **4 passed**. Three public landing tests covered desktop, mobile, and reduced motion. One Chromium test covered synthetic signed-in onboarding, CSV import, dashboard match, investigation, simulated hold, refresh persistence, and mobile investigation layout with mocked Auth/API responses. It does not prove live Supabase or network API integration.
- `npx tsc --noEmit`: passed. `npm run build`: passed, with 15 app routes generated. No lint script or ESLint configuration exists, so lint was **not run**.
- `docker compose --env-file web/.env.local config -q`: passed static validation. `docker info` could not connect to Docker Desktop's Linux engine; container build/start was **blocked**.
- Live local web at `http://localhost:3000/` and API at `http://localhost:8000/health` responded HTTP 200. The running API's OpenAPI schema showed explicit `account` is required, confirming the updated API was loaded. The processes were not restarted by this verification; use the startup commands for a clean run.
- `git check-ignore` confirmed both private env files are ignored. Targeted history lookup found no committed `api/.env`, `web/.env.local`, or root `.env`. The web Docker build context now excludes env files. Secret values were not printed.

## Blocked or unverified

- **Live Supabase Auth journey:** no disposable confirmed account credentials or admin cleanup path were available. Signup, login, logout, session refresh/expiry, and two-account browser isolation remain unverified by this agent. The user's earlier manual success is separate evidence.
- **Live PharmaOne BYOK TinyFish sync:** the configured PostgreSQL database contained zero connected user keys. Status: **LIVE TINYFISH VERIFICATION PENDING**. The prior connector snapshot does not test the application's paid sync endpoint.
- **Docker runtime:** Docker daemon unavailable. Static Compose validation is not a container startup test.
- **Lint:** no configured command. Production HTTPS, backups, managed schema migrations, provider billing/rate limits, and full historical CDSCO coverage need production work.

## Next evidence needed for full acceptance

Use two disposable, confirmed Supabase accounts and connect one TinyFish key through Settings. Store test credentials only in an ignored local file or password manager; never paste them into chat or commit them. A single explicit period/limit sync can then verify the paid BYOK path. Start Docker Desktop if container runtime verification is desired. See [manual testing](FINAL_MANUAL_TESTING.md) and [known limitations](KNOWN_LIMITATIONS.md).
