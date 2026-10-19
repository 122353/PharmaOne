# PharmaOne final technical handoff

## Scope completed locally

The sprint was completed in `D:\PharmaOne - Copy` against the project SQLite development database. It did not deploy, commit, push, modify a hosted database, access a production environment, call TinyFish or Sarvam, or reset the demo database.

The preserved local baseline contains five regulatory alerts, three inventory rows, two stored matches, two notifications, and no live-source timestamp. The imported source is labelled as an AUG-2026 historical snapshot.

## Delivery status

| Area | Status | Evidence or next owner action |
|---|---|---|
| Deterministic matching and notification lifecycle | TESTED | Unit, database-only integration, and offline evaluation coverage are present. |
| JWT, tenant boundaries, and rate limiter | TESTED | Claims, owner-scoped access helpers, limiter concurrency, and rate-limit behavior have local coverage. |
| Scheduled ingestion and offline playback | TESTED | Disabled-by-default policy, budgets, locks, retry limits, provenance, and in-memory replay are covered. |
| PostgreSQL migration package | PARTIALLY TESTED | SQL guards and disposable-runtime harness pass static/local checks; actual PostgreSQL execution is pending. |
| Frontend type check | TESTED | `npx tsc --noEmit` passed on 19 October 2026. |
| Frontend production build and current browser rerun | BLOCKED | Sandbox denied output-directory creation and loopback sockets required by the runners. |
| Hosted deployment, live monitoring, and paid-provider verification | NOT IMPLEMENTED | These require explicit operational approval. |

## Main implementation changes

- `api/app/auth.py` verifies asymmetrically signed Supabase JWTs with issuer, audience, expiry, subject, and role requirements.
- `api/app/rate_limit.py` adds bounded process-local limits for sensitive authenticated operations and returns `Retry-After` on `429`.
- `api/app/matching.py` adds explainable deterministic gates for batch, manufacturer, strength, dosage form, release, malformed strength text, and ingredient combinations. Optional MiniLM similarity is review-only.
- `api/app/semantic_matching.py` keeps MiniLM CPU-only and local-files-only, bounds the embedding cache, and serializes cold model construction.
- `api/app/scheduled_ingest.py` provides a strict disabled-by-default one-shot scheduler and an in-memory `--playback` rehearsal.
- `api/app/ingest_service.py` records source provenance, bounds provider attempts and records, serializes local runs, and reruns matching after accepted source changes.
- `api/migrations/001_monitoring_notifications.sql` and `002_ingestion_run_provenance.sql` provide additive PostgreSQL changes with compatibility checks; `api/migrations/validate_postgres.py` validates them only against disposable local targets.
- `web/e2e/notifications.spec.ts` covers source labels, Hindi acknowledgement rollback, missing manufacturer review state, and notification behavior with mocked local API responses.

## Verification record

The following commands were executed using `PHARMAONE_ENV=local` and `DATABASE_URL=sqlite:///./pharmaone_development.db` where the command uses the API.

| Command or check | Result |
|---|---|
| Matching, semantic cache, evaluation, and scheduled-ingest focus | 69 passed |
| Database-only backend group | 139 passed, 4 PostgreSQL tests skipped, 2 TestClient tests deselected, 1 deprecation warning |
| JWT claim tests | 5 passed, 1 TestClient test deselected |
| Rate-limit core tests | 2 passed, 1 TestClient test deselected |
| Offline matcher evaluation | 24 synthetic pairs; rules and enhanced final precision/recall/F1 were 1.000/1.000/1.000; enhanced retrieval recall was 1.000 |
| TypeScript | `npx tsc --noEmit` passed |
| Previous mocked notification browser run | 8 passed in 26.8 seconds before the current sandbox restriction surfaced |

The matcher results are synthetic and not clinical validation. See [matching evaluation](matching-evaluation.md) for labels, individual predictions, timing, memory, and deployment decision.

## Current execution blockers

1. There is no usable local PostgreSQL runtime. Docker's Linux engine was unavailable and local PostgreSQL binaries were absent. The disposable migration validator and hosted-role smoke checks remain required before deployment approval.
2. The current sandbox blocks Windows loopback socket-pair creation. A bounded `socket.socketpair()` probe timed out, which prevents FastAPI TestClient and Playwright from starting. This is an environment blocker for the remaining API/browser reruns.
3. The Next production build can type-check but cannot create `.next` or an ignored alternate output directory, returning `EPERM`. The original Next configuration was restored after the diagnostic attempt.

## Operational handoff

- Follow [the production runbook](PRODUCTION_DEPLOYMENT_RUNBOOK.md) for database backup, migration, configuration, scheduler, smoke test, and rollback sequencing.
- Follow [the security review](SECURITY_REVIEW.md) for controls, known limitations, and pre-production actions.
- Follow [the monitoring design](MONITORING_DESIGN.md) for source freshness, ingestion, matching, notification, and observability behavior.
- Follow [the migration guide](../api/migrations/README.md) for safe disposable PostgreSQL validation.

## Next actions requiring approval or environment access

1. Restore a local PostgreSQL runtime and run the disposable migration validator.
2. Restore loopback socket access, then rerun the FastAPI TestClient suite and Playwright suite.
3. Resolve the local filesystem permission that prevents Next build output creation, then run the production build.
4. After the prior items pass, obtain explicit approval before any hosted migration, deployment, scheduler enablement, or live provider call.
