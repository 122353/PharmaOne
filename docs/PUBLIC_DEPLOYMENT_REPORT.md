# PharmaOne public deployment readiness — 18 October 2026

## Current state

The application is locally reachable at `http://localhost:3000/`; the API responds at `http://localhost:8000/health`. Public Vercel and Render URLs do not exist yet. Public deployment has not been approved or performed. Git has no remote and there is no PharmaOne project in the authenticated Vercel account. Render account authentication and billing settings have not been verified.

## Implemented and verified locally

- Next.js landing, Auth UI, onboarding, inventory, CDSCO evidence, dashboard, scan, ContextOS, investigations and simulated holds.
- Browser Tesseract.js image OCR on a generated synthetic medicine label. Raw text is shown; identifiers require manual confirmation before server matching. The packaging image is processed in the browser. The ordinary scan page does not call paid Sarvam OCR.
- PharmaMatch v1 logistic product-similarity model and PharmaClassify v1 naive Bayes quality-finding model, trained locally from disclosed synthetic examples. Runtime artifacts are JSON and use Python standard-library inference. Synthetic holdout scores are 12/12 and 6/10. This does not establish real-world accuracy. Scores and categories are advisory; exact batch/manufacturer checks and pharmacist review remain authoritative.
- Previously retrieved ten official CDSCO NSQ records from one approved TinyFish `AUG-2026` run remain in the configured Supabase PostgreSQL database with source URL and retrieval time. The earlier read-only source comparison is in `evidence/cdsco-live-compare-2026-10-18.json`. No new TinyFish or Sarvam paid call was made during this deployment preparation.
- Tenant isolation, direct client-role table denial and rollback-protected synthetic workflow tested against the configured PostgreSQL database.
- Render Free blueprint and Vercel build configuration; production settings reject SQLite and insecure origins. Hosted blueprint has no paid-provider keys.

## Actual test evidence

- Backend: `python -m pytest tests -q` → 102 passed, 3 optional PostgreSQL tests skipped, 1 upstream deprecation warning.
- PostgreSQL opt-in: 3 passed with rollback-protected synthetic records.
- Browser: `npm test` → 9 passed, including real local Tesseract recognition of a generated image and a mocked signed-in pharmacy journey through investigation and simulated hold after refresh.
- TypeScript: `npx tsc --noEmit` passed.
- Production frontend: `npm run build` passed using Next.js webpack. Repeat Turbopack builds hit a local Windows worker-process error, so `build` now uses the supported `--webpack` option.
- Secret scan: three configured secret values checked; none found outside ignored local env files. This check is limited to configured values and is not a full independent security audit.
- Local one-worker API with both model artifacts loaded: 90.8 MB working set, 71.9 MB private memory. Twenty local `/health` requests: median 2.9 ms, p95 8.8 ms, maximum 17.3 ms. This does not predict Render cold starts or production database latency.

## Not yet verified publicly

- Vercel and Render provisioning, GitHub push deployment and provider billing settings.
- Render URL and cold start, Vercel URL, CORS, Supabase Auth redirects, live signup/login, two real accounts and public end-to-end persistence.
- Real phone camera and real medicine packaging OCR quality.
- PharmaMatch/PharmaClassify accuracy on representative labelled regulatory and pharmacy datasets.
- Continued TinyFish retrieval on the hosted API. Under the ₹0 target, the blueprint intentionally omits the key; the stored official snapshot remains available. No continuous monitoring is claimed.

## Remaining actions after approval

1. Verify GitHub and Render login and that selected Render and Vercel resources are Free/Hobby with no payment method or overage billing.
2. Create a private GitHub repository; check exactly which files are committed; push the reviewed branch. Connect that repository to Render and Vercel. Preserve `.env` files outside Git.
3. Create Render from `render.yaml`; enter only `DATABASE_URL`, `SUPABASE_URL` and exact HTTPS `ALLOWED_ORIGINS` in provider secret prompts. Select the free plan and one worker. Do not enter TinyFish or Sarvam keys.
4. Create Vercel project with root directory `web`; set `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Link the approved branch and verify Hobby plan.
5. Add the final Vercel hostname to Supabase Auth site URL/redirect allowlist. Use an existing confirmed test user or disposable accounts for live signup, inventory, scan, alert, investigation, refresh and cross-tenant checks.
6. Record public URLs, cold-start measurements and any defects in this report. If any provider requires payment or broader permissions, stop before provisioning.

## Local launch

```powershell
cd D:\PharmaOne\api
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

In another terminal:

```powershell
cd D:\PharmaOne\web
npm ci
npm run dev
```
