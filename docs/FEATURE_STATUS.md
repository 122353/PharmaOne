# PharmaOne feature status — 19 October 2026

This page summarizes the local SQLite audit. Older PostgreSQL and ten-record claims in historical reports describe earlier environments. See the [current verification report](FINAL_VERIFICATION_REPORT.md) for test results and limits.

## Tested locally

- **Matching — TESTED.** Exact batch comparison, strength conflict detection, conservative manufacturer normalization, formulation/release checks, and missing-critical-field review are covered by regression tests.
- **Notifications — TESTED.** Pharmacy-scoped listing and acknowledgement, unread counts, idempotency, event deduplication, stale-event deactivation, persistence, and Review navigation have isolated API and browser coverage.
- **Historical source — TESTED.** The current SQLite baseline has five verified AUG-2026 regulatory records. The dashboard labels the import historical and reports no live source check.
- **Frontend — TESTED.** TypeScript check, production build, and the full 12-test Playwright suite passed. UI checks include notification history, error/retry, alert routing, and strength-conflict messaging.
- **Schema compatibility — TESTED on SQLite.** Local additive repairs preserve existing rows and indexes; PostgreSQL SQL is prepared but not executed.
- **Dependency audit — TESTED.** `npm audit` and `pip-audit` report zero known vulnerabilities after the cryptography version update.

## Partially verified

- **MiniLM — PARTIALLY TESTED.** Optional local candidate retrieval surfaced one synthetic candidate for human verification. It cannot promote a match. The 18-case evaluation is preliminary; process RSS reached about 521 MiB.
- **Monitoring — PARTIALLY TESTED.** Historical snapshot import, version/provenance handling, rematching, and notification deduplication are implemented and tested locally. No live TinyFish request or scheduled check was made.
- **Security — PARTIALLY TESTED.** JWT and tenant checks, bounded uploads, CORS, CSV validation, query safety, server-side provider keys, secret scans, and dependency audits were reviewed. There is no general API rate limiter or malware scanner.

## Not run or not implemented

- **Live providers — NOT RUN.** No paid TinyFish or Sarvam request was made. Live OCR/translation and signed-in browser acceptance were not repeated.
- **PostgreSQL migration — PARTIALLY TESTED.** Migration scripts are additive and repeatable, but no isolated PostgreSQL server was configured, so PostgreSQL DDL/RLS tests were skipped.
- **Scheduling — NOT IMPLEMENTED.** A bounded one-shot job design is documented; no polling schedule is enabled.
- **Production changes — NOT IMPLEMENTED.** Existing public deployment and Supabase configuration were not changed or assessed in this local task.
