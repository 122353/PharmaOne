# Production change checklist

**Status on 19 October 2026: no production change was authorized or performed in this task.** The existing public deployment described by the user must remain unchanged. The earlier checked boxes and approval language in this file were historical and are superseded by this status.

Before a future production change:

1. Obtain explicit approval for the exact target, action, change window, and rollback owner.
2. Prepare an isolated staging environment and verify its database URL, auth project, CORS origins, and provider keys.
3. Review the additive migrations in [the migration guide](../api/migrations/README.md), take a backup, and verify a staging restore before applying any hosted PostgreSQL DDL.
4. Confirm billing/spend limits and obtain separate approval before any paid TinyFish or Sarvam request. Do not enable recurring provider polling without a kill switch and budget ceiling.
5. Run backend tests against SQLite and isolated PostgreSQL, TypeScript, production build, browser tests, npm/pip audits, and secret scans.
6. Verify authenticated tenant isolation, HTTPS, SMTP, logging, backups, monitoring, and key rotation with disposable test accounts.
7. Record approvals, migration IDs, health results, rollback outcome, and the verified public URLs.

No command in this repository task applies this checklist or changes the existing public deployment. See [current deployment readiness](DEPLOYMENT_READINESS.md).
