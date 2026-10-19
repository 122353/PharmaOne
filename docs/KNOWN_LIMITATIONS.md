# Known limitations and verification status

## Current verified scope

- **Historical evidence — TESTED.** The local SQLite baseline contains five verified CDSCO records for AUG-2026, three synthetic inventory rows, two potential matches, and two acknowledged notifications. The dashboard labels the evidence as a historical snapshot and shows that no live check is recorded.
- **Matching — TESTED.** Exact normalized batch equality and conservative product/manufacturer/strength checks determine status. Missing critical information is routed to `needs_verification`; a conflicting batch is not fuzzy-matched. A potential match is not physical confirmation or a safety clearance.
- **MiniLM — PARTIALLY TESTED.** The optional cached model is local-only and can surface one synthetic naming candidate for review. It cannot authorize `potential_match`. Its process RSS was about 520.9 MiB after load in the local evaluation, so it is not enabled by default or suitable to add blindly to a low-memory production backend.
- **Notifications — TESTED.** Pharmacy scoping, deduplication, active-state handling, idempotent read acknowledgement, dashboard counts, and persisted read state are covered by automated SQLite/API tests and browser tests. The current saved baseline has zero unread notifications because both events are already acknowledged.
- **Frontend — TESTED.** TypeScript, production build, and synthetic browser journeys cover notification count/read behavior, source period, retry state, alert navigation, and strength-conflict messaging.
- **Migration — PARTIALLY TESTED.** Repeatable additive PostgreSQL SQL and rollback guidance are prepared. SQLite compatibility repair is exercised against isolated databases. PostgreSQL DDL, grants, and RLS were not executed against an isolated PostgreSQL server in this task.
- **Security — PARTIALLY TESTED.** JWT signature/issuer/audience/role verification, pharmacy scoping, upload bounds, CSV validation, parameterized queries, server-side provider credentials, exact-origin CORS rules, notification ownership, and safe errors were inspected or tested. No high-confidence credential pattern was found in tracked files or reachable Git history; ignored environment files were not read or printed.
- **Dependencies — TESTED.** JavaScript `npm audit` and Python `pip-audit` report zero known vulnerabilities after the project upgraded `cryptography` from the vulnerable 46.0.7 range to `50.0.2`. The Python audit tool is listed as development-only; it is not added to production requirements. See the [upstream cryptography advisory](https://github.com/pyca/cryptography/security/advisories/GHSA-537c-gmf6-5ccf) and [PyPI release](https://pypi.org/project/cryptography/50.0.2/).

## Remaining limits

- The August 2026 snapshot is historical evidence; there is no active polling, complete CDSCO archive pagination, or deletion detection. No paid TinyFish call was made. Freshness must not be represented as live monitoring.
- TinyFish ingestion is operator-controlled and limited to one reporting period and at most 25 rows. A future scheduler must have explicit budget caps, overlap prevention, idempotency, provenance, and a kill switch. Nothing is scheduled.
- The synthetic matcher dataset has only 18 curated cases. Its perfect rule score is a regression result, not a general accuracy claim. PharmaMatch is synthetic and advisory; MiniLM threshold 0.70 is preliminary and not calibrated.
- The MiniLM model has a high memory footprint and depends on a local cache. Without the opt-in flag/model, matching falls back gracefully to the deterministic and lightweight path.
- PostgreSQL integration tests were skipped because no isolated PostgreSQL test database was configured. The production migration remains unapplied. Production deployment, Supabase schema/configuration, and production data were untouched.
- Live Supabase signup/reset and a two-account browser acceptance were not repeated. The browser tests use a synthetic session and mock API responses.
- Live Sarvam OCR, translation, and chat acceptance were not performed. Browser OCR and provider adapters have synthetic or mocked coverage only. Physical camera use and printed-code scanning remain untested.
- Custom SMTP delivery has not been verified.
- Investigation attachments have tenant checks and basic image/PDF validation, but there is no antivirus scan or full PDF parser. Object storage is not implemented.
- There is no general API rate limiter. Authenticated mutation routes and provider/upload bounds provide some protection, but broader abuse controls and production monitoring remain deployment work.
- Docker runtime, hosted HTTPS ingress, production backups/restore, and production deployment were not tested. Docker static config is not evidence of a running container.
