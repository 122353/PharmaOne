# PharmaOne security review

Reviewed on 19 October 2026 for the local technical completion sprint. This review covered source code, local tests, dependency-audit results recorded during the sprint, and local configuration boundaries. It did not access production services, secrets, or live provider accounts.

## Security status

| Area | Status | Evidence or remaining condition |
|---|---|---|
| JWT verification and owner scoping | TESTED | Unit and local integration coverage validates asymmetric tokens, claims, role checks, malformed identifiers, and tenant boundaries. |
| Sensitive-route rate limits | TESTED | Process-local limiter has deterministic and concurrency coverage. |
| CSV and attachment input controls | TESTED | Size, type, formula, image, and basic PDF rejection paths have local coverage. |
| Dependency checks | TESTED | `npm audit` and `pip-audit` were clean after the local runtime update; `pip check` passed. |
| PostgreSQL RLS and role enforcement | BLOCKED | SQL and catalog checks exist, but no local PostgreSQL runtime was available. |
| Production penetration and live auth testing | NOT IMPLEMENTED | No production endpoint, user account, provider, or deployment was touched. |

## Authentication and authorization

`api/app/auth.py` accepts only validated asymmetric JWTs and requires signature validation, issuer, audience, expiration, subject, and the authenticated role. It rejects unsupported signing algorithms and oversized bearer values. The issuer is derived from the configured Supabase URL; token data is not trusted before validation.

Private API records are pharmacy-owned. Route helpers resolve the authenticated user's pharmacy and return safe absence responses for guessed or cross-tenant identifiers. Regulatory source records are intentionally shared reference data; inventory, matches, notifications, investigations, attachments, suppliers, and import history are scoped to the pharmacy.

The frontend configuration uses public Supabase values only. No service-role value is referenced in the web source. Provider integrations stay server-side and the sprint did not invoke TinyFish or Sarvam.

## Abuse controls

`api/app/rate_limit.py` applies a bounded 60-second window to sensitive authenticated operations. It keys limits from the verified user subject rather than a forwarded header, returns `429` with `Retry-After`, and bounds retained keys. Current limits cover provider-facing requests, uploads and attachments, matching/scan requests, and other writes.

The limiter is deliberately in process. Limits reset when the API restarts and are independent in each worker or instance. A multi-instance deployment needs an approved shared limiter before treating these limits as service-wide abuse protection.

## Input and file handling

CSV uploads are capped at 2 MiB and 5,000 rows, require the expected headers, reject spreadsheet-formula prefixes, bound field lengths and quantity, and validate ISO expiry dates. Imports preserve incomplete rows for review where identifiers are missing; matching independently rejects malformed, missing, or contradictory strength evidence from promotion.

Attachment uploads are capped at 2 MiB. PNG and JPEG payloads are decoded with Pillow, and PDFs receive lightweight header/trailer checks. Files are pharmacy-scoped and downloads use safe failure behavior. This is format validation, not antivirus scanning or full PDF sanitization. Production use needs an approved malware-scanning and retention design.

## Matching safety

The matching path uses deterministic batch, manufacturer, strength, dosage-form, and release checks. Batch punctuation is significant. A model can only retrieve a candidate for pharmacist review after the deterministic gates; it cannot create a `potential_match`.

The reviewed regressions include zero or negative strength denominators, malformed nonempty strength fields, contradictory name/field strengths, combinations, dose conversions, formulation conflicts, and concurrent optional model startup. A malformed inventory row is retained as a review case and does not break rematching of valid inventory.

## Source, SSRF, and provider boundaries

The regulatory adapter uses its fixed official source URL and the configured provider adapter. There is no public endpoint that accepts an arbitrary destination URL for provider retrieval. Historical playback reads verified project evidence into an in-memory database and reports itself as historical; it does not call a provider.

Live ingestion is one-shot and disabled by default. It has request, record, retry, and frequency bounds, serializes local runs, stores sanitized failures, and records source provenance. Calling a paid provider or enabling the scheduler remains an approval-gated operational action.

## Database and deployment controls

SQLite is the local development target. PostgreSQL startup refuses to create schema implicitly and verifies only the required tables and columns. The two PostgreSQL migration files are additive, transactional, and include catalog checks that refuse weak pre-existing prototypes. The notification migration enables RLS and revokes direct `PUBLIC`, `anon`, and `authenticated` table privileges.

Those SQL controls are not evidence of deployed RLS or role behavior until the disposable local PostgreSQL validator and an approved deployment-role smoke check have run. See [the migration guide](../api/migrations/README.md) and [the deployment runbook](PRODUCTION_DEPLOYMENT_RUNBOOK.md).

## Verification limits

The current sandbox blocks Windows loopback socket pairs: a two-second `socket.socketpair()` probe timed out and IPv6 loopback was denied. That prevented the current FastAPI TestClient and Playwright reruns from starting. Database-only backend tests, matching tests, type checking, and offline evaluation remained runnable. This is an environment restriction, not a basis to infer API or browser failures.

The current Next production-build process also could not create output directories under either `.next` or an ignored alternate output directory, returning `EPERM`. No source configuration was retained from that attempted workaround.

## Required production actions

1. Run the disposable local PostgreSQL migration validator and resolve any role, RLS, constraint, or catalog failure.
2. Perform an approved two-account browser/API acceptance test using confirmed Supabase identities.
3. Add shared rate limiting before multi-worker or multi-instance use.
4. Add malware scanning and a retention policy before accepting production evidence uploads.
5. Review secret rotation, backup restore, monitoring, alerting, and access logs with the production owners.
