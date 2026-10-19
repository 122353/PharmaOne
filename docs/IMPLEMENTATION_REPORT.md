> **Historical report.** The dated notes below describe earlier test and provider environments, including PostgreSQL and ten-record claims. They are not the 19 October local SQLite baseline. Use the [current verification report](FINAL_VERIFICATION_REPORT.md) for present counts, tests, and production status. The existing public deployment was not changed in this task.

# PharmaOne implementation report — 18 October 2026

## Final verification addendum

- Signup now prevents duplicate submissions, disables the button while pending, gives specific email-rate-limit guidance, and uses explicit confirmation and password-reset redirect URLs. A reset-password page accepts a Supabase recovery session and lets the user set a new password. Real mail delivery still requires custom SMTP configuration by the project owner; see [email setup](SUPABASE_EMAIL_SETUP.md).
- Investigation decisions are idempotent for the same effective state. Review status, physical verification and simulated hold are separate fields in API responses and in both activity views. A hold no longer overwrites a reviewed/closed decision. The browser blocks double clicks and refreshes audit events immediately. Historical events are preserved.
- Evidence uploads reject malformed images, oversized files, mismatched MIME and PDFs missing basic trailer markers; downloadable files remain tenant scoped and `no-store`. These checks do not replace antivirus or a full PDF parser.
- The ten stored records from the successful `AUG-2026` TinyFish run were read-only compared against the current official CDSCO public table. Ten exact batch/period rows were found; product, batch, finding, period and reporting-source fields matched. Two manufacturer values differed only in whitespace. The [field-level JSON evidence](../evidence/cdsco-live-compare-2026-10-18.json) includes the exact values, source URL and stored retrieval timestamps. No new TinyFish synchronization or other paid call was made in this pass.
- Docker Compose now has API/web health checks and binds all published ports to localhost. The Next.js server adds `nosniff`, frame denial, referrer and browser-permission headers. Compose parsed, but the unavailable Docker engine prevented a container boot.
- A synthetic browser workflow now covers OCR field correction, ContextOS English/Hindi, review, evidence upload, simulated hold and refresh persistence. It uses mocked Auth/API responses and is not a live provider or two-account acceptance test.
- The language provider now persists across the entire app instead of remounting per signed-in route. Auth, password recovery, dashboard and key scan/ContextOS screens gained local Hindi text; the signup browser test verifies the preference survives reload. Other legacy screens remain partially English.

**Current test evidence:** 99 backend tests passed, 3 opt-in PostgreSQL tests skipped in that run, then all 3 PostgreSQL integration/security tests passed separately. TypeScript, eight Playwright tests and the Next.js production build passed. Local API `/health` and web `/` returned HTTP 200 after restart. The remaining acceptance work is a second confirmed Supabase account, verified SMTP, one approved live OCR/translation call each, a physical camera check and Docker runtime when available.

The sections below preserve the earlier implementation chronology. Statements describing an earlier unverified Sarvam answer or source comparison are historical; the addendum and [final verification report](FINAL_VERIFICATION_REPORT.md) contain the current result.

## Preserved functionality

The existing Next.js landing, Supabase authentication, pharmacy onboarding, CSV upload and correction, source backed alerts, deterministic inventory matching, dashboard, investigations, simulated holds, and audit events remain. PostgreSQL retains the earlier verified snapshot and ten records from the central `AUG-2026` synchronization. No pharmacy records were deleted.

## Implemented in this pass

- Central TinyFish backend key and operator-only, bounded single-period synchronization. User key and paid-sync routes were removed. PostgreSQL advisory lock prevents concurrent commands. Validated records retain public CDSCO URL, retrieval time, run ID, and source period.
- PostgreSQL RLS enabled on every application table and direct `anon`/`authenticated` privileges revoked. FastAPI remains the only application data gateway. Applied to the configured Supabase database without resetting records.
- Sarvam HTTP adapter for chat, document extraction OCR, and short-text translation with server-side key, timeouts, response checks, bounded retry, usage limits at API entry points, and sanitized errors.
- ContextOS endpoint using authenticated pharmacy matches and official alert evidence. Returns source citation and exact identifiers separately from AI text. Missing model, invalid output, or missing evidence yields labeled evidence-only responses.
- Scan UI with ZXing QR/barcode camera decoding, camera capture, PNG/JPEG upload, Sarvam extraction, original extracted text, field correction, and confirmation before CDSCO matching. Barcode-only input never invents a batch.
- English/Hindi selector persisted locally; translated navigation and key scan/ContextOS text. Sarvam translation endpoint for alert findings keeps original wording and exact batch alongside the translation.
- Meaningful source version hashes, added/updated change history, and pharmacy-specific inventory impact indicators.
- Investigation statuses, persistent audit checklist flags, and private PostgreSQL-backed evidence attachments (PNG/JPEG/PDF up to 2 MB); simulated holds remain simulation only.
- Tenant-scoped synthetic supplier routes and exposure view; shared CSV/mock ERP import pipeline and private import history.
- Final-preparation fixes: invalid/empty source syncs now fail without changing alerts; duplicate rows in one provider result are ignored; ContextOS requires an explicitly selected alert and never silently sends an unrelated global record to Sarvam. The privacy notice and feature documentation now describe the central TinyFish model. The unused BYOK encryption helper was removed without changing its legacy database table.
- ContextOS follow-up: Sarvam Chat 105B now disables reasoning for short, bounded replies and checks `finish_reason`. Evidence-only fallback reasons distinguish truncation, provider errors, invalid responses, timeouts, rate limits, missing/wrong batches, and unsupported regulatory orders. Only fixed reason codes enter logs and audit events. English and Hindi negative-recall phrasing passes; unsupported recall or dispensing instructions remain blocked.
- The next user-initiated ContextOS request reached validation and its audit outcome was `invented_batch`. The generated wording was intentionally not retained, so its exact cause is unknown. The validator was repaired to avoid interpreting ordinary phrases such as "batch has" and "batch of" as batch identifiers while still rejecting a second numeric or explicitly labelled batch. This repair passed local tests; a successful live Sarvam answer still needs a separately approved request.
- On 18 October 2026, the user approved one bounded ContextOS live retest for the selected `VRNT-933` alert. Preflight confirmed a configured Sarvam key, one CDSCO-backed alert, one matched pharmacy, and room under the daily cap. One Sarvam POST was made through the ContextOS handler. The persisted audit and response both recorded `unsupported_regulatory_order`; the UI-safe response was `evidence_only` with the official CDSCO source and `potential_match` inventory status. Raw provider text was not retained, so this result does not prove whether the model made an unsupported claim or the validator produced a false positive. No retry was made.
- After the failed-safe live check, a separate local validator defect was found: negative statements like "This is not a recall order" were rejected. The negation check now accepts those statements and still rejects affirmative recall/dispensing claims. This was tested without another paid request; whether it addresses the exact live failure remains unknown.
- ContextOS now asks Sarvam for only one or two sentences about the exact batch and listed quality finding; the application separately presents the official source and safety caveat. After 27 passing local ContextOS tests, the user approved up to three additional live text calls. The first returned "Batch VRNT-933 was flagged for Dissolution." with `finish_reason=stop`; ContextOS returned `mode=sarvam`, `fallback_reason=null`, and a separate database read confirmed the persisted audit outcome `success` at 2026-10-18 09:26:22 UTC. The other two authorized calls were not used. Browser control was unavailable in this session, so this acceptance exercised the real handler, database, and provider, not a signed-in browser submission.
- Synthetic QR and EAN-13 fixtures verify ZXing decoding; a product-only barcode leaves batch blank. Camera startup/stop race handling was repaired. Alert, investigation and change pages show loading states instead of premature empty states.

## Main files

Backend: `api/app/main.py`, `db.py`, `models.py`, `ingest_service.py`, `ingestion.py`, `inventory_service.py`, `sarvam.py`, `contextos.py`, `scan.py`, `suppliers.py`. Frontend: `web/components/AppShell.tsx`, `TranslatedFinding.tsx`, `web/lib/language.tsx`, `web/lib/scan.ts`, and routes `scan`, `contextos`, `alerts`, `investigations`, `changes`, `connectors`, `suppliers`. Tests: `api/tests/test_*.py`, `web/e2e/workflow-mocked.spec.ts`, `web/e2e/symbol-fixtures.spec.ts`. Configuration and operations: `.env.example`, `scripts/configure_local.py`, `README.md` and this `docs` folder.

## Database changes

Added `supplier_links`, `inventory_imports`, and `investigation_attachments` tables. Existing tables and source rows were retained. Startup creates missing tables, enables RLS, and revokes browser-client direct table privileges. The earlier `tinyfish_connections` table remains for non-destructive legacy retention, but no pharmacy API reaches it. Versioned migrations are still needed before a production rollout.

## Provider status

Both `TINYFISH_API_KEY` and `SARVAM_API_KEY` are configured in the ignored local backend environment. The user confirmed a live central TinyFish run for `AUG-2026`; the PostgreSQL run `c4f6314f-8d7d-4664-854d-053384dc042d` is `succeeded` with 10 records. All ten current alerts from that run have distinct fingerprints, source URLs and retrieval timestamps. This check did not independently compare every field against the CDSCO website. Earlier Sarvam calls returned safe evidence-only fallbacks (`invented_batch` and `unsupported_regulatory_order` for two audited calls). After tightening the prompt and repairing local false positives, one approved live Sarvam text call produced a grounded answer for `VRNT-933`; ContextOS accepted it and persisted `success`. The generated sentence was inspected only in the local test process, not saved in application logs or audit records.

Sarvam request schemas were checked against the official [chat](https://docs.sarvam.ai/api-reference/chat/chat-completions-v1), [document extraction](https://docs.sarvam.ai/api-reference/doc-ai/job/extract), [job results](https://docs.sarvam.ai/api-reference/doc-ai/job/results), and [translation](https://docs.sarvam.ai/api-reference/text/translate-text) documentation. The chosen model IDs have not been checked against a configured account.

## Bounded live acceptance plan (requires separate approvals)

- **Chat:** One `POST /v1/chat/completions` using `sarvam-105b`, `reasoning_effort: null`, and `max_tokens: 400`, tied to the selected `VRNT-933` alert. Paid POST requests are not retried, including on HTTP 429. The app records only a fixed outcome code; inspect token use in the provider dashboard. Raw model output is not logged. Price is account-dependent and not assumed here.
- **OCR:** One `POST /doc-ai/v1/job/extract` with a synthetic packaging image, followed by at most 12 status reads and one result read. No paid POST retry. Confirm every extracted field before matching; price is unverified.
- **Translation:** One `POST /translate` for a short synthetic English finding into Hindi, with no paid POST retry. Verify original and translated text and exact structured identifiers. Price is unverified.
- **TinyFish:** No repeat request is needed for the current acceptance work; the completed ten-record run can be checked locally and on the official CDSCO site.

## Verification

- **PASSED:** 85 backend tests (three opt-in PostgreSQL tests skipped in the default run), 14 affected Sarvam adapter tests after the final no-retry change, and three PostgreSQL integration/security tests separately; 18 October 2026. Run PostgreSQL checks sequentially to avoid schema-startup lock contention.
- **PASSED AFTER VALIDATOR/PROMPT REPAIRS:** 27 ContextOS tests, including prose after "batch", wrong numeric/labelled batches, negated recall statements, unsupported regulatory orders, and the constrained prompt. The local API was restarted with the repaired code.
- **PASSED:** TypeScript type check, Next.js production build, and seven Playwright tests covering the synthetic workflow, landing, mobile layout, reduced-motion behavior, QR decoding, product-only EAN-13 decoding, and invalid-symbol rejection.
- **PASSED:** Both provider keys remain only in ignored backend environment files; a local scan found neither key in 100 project source files or 27 built browser JavaScript assets. Docker Compose configuration parses.
- **LIVE VERIFIED:** One central TinyFish `AUG-2026` run completed and ten current source records persisted. The user's frontend check confirmed they appeared in the application.
- **LIVE VERIFIED:** One Sarvam Chat 105B response for the selected `VRNT-933` official alert passed ContextOS validation and persisted a `success` audit. API and ContextOS page both return HTTP 200 locally. Signed-in browser acceptance, OCR, and translation still require separate checks.
- **BLOCKED:** Docker container boot; Docker Desktop Linux engine unavailable.
- **MANUAL TEST REQUIRED:** The user reports successful one-account signup, onboarding and inventory upload. A live two-account isolation check and physical camera scan remain open.

See [feature status](FEATURE_STATUS.md), [manual checklist](FINAL_TESTING_CHECKLIST.md), and [limitations](KNOWN_LIMITATIONS.md). The verdict is **PARTIALLY VERIFIED — BLOCKERS REMAIN**.
