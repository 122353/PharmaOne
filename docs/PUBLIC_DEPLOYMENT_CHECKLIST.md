# ₹0 public deployment checklist

Status on 18 October 2026. This checklist tracks the requested Vercel + Render + existing Supabase architecture. Creating this file does not deploy anything.

- [x] Inspect Next.js, FastAPI, Supabase, TinyFish, Sarvam, Docker, tests and local env structure; preserve existing records and uncommitted work.
- [x] Confirm prior live TinyFish run and ten stored official CDSCO rows; do not spend another retrieval credit for this deployment.
- [x] Add browser Tesseract.js OCR with raw text, manual correction, and server-side identifier verification. Retain optional server Sarvam OCR only as a separate paid path.
- [x] Verify browser OCR with a real synthetic image and production build; phone viewport was verified on landing. Physical phone camera remains unverified.
- [x] Train small PharmaMatch and PharmaClassify advisory models from synthetic examples; store reproducible JSON artifacts, expose real inference, and retain hard batch/manufacturer checks. Synthetic holdout was 12/12 and 6/10 respectively; real-world validation remains open.
- [x] Add Render Free API configuration and Vercel frontend configuration without including secrets in Git.
- [x] Verify backend memory and latency locally with both models loaded: 90.8 MB working set, 71.9 MB private memory; 20 `/health` requests median 2.9 ms, p95 8.8 ms. Measure public cold start after deployment.
- [x] Run backend (102 passed, 3 opt-in skipped), PostgreSQL (3 passed), TypeScript, browser (9 passed), webpack production-build and secret-scan regression checks. Local Turbopack repeat builds hit a Windows child-process error; the supported webpack build passed and is now the deployment build command.
- [ ] Confirm Vercel, Render and Supabase authentication and zero-charge account settings. Vercel CLI is authenticated to `rupeshnitya-8731` on a Hobby team; the `pharmaone-ai` project is linked to `web/`, and its two browser-public Supabase settings are configured for Production and Preview. Render account and billing settings are not yet verified. Do not add a payment method or enable billing.
- [ ] Identify and connect an authorized GitHub remote. The current repository has no remote; no provider can auto-deploy it yet.
- [ ] Obtain the Render HTTPS URL; configure Vercel's public API URL and exact backend CORS origin. Configure Supabase Auth redirect URLs for the final frontend hostname.
- [ ] Verify both public URLs, authenticated persistence, browser OCR, matching, official evidence, investigation and tenant isolation using disposable accounts.
- [ ] Record URLs, tests, RAM/latency, known defects and blocked items in the final report.

The two new models are trained only on disclosed synthetic examples, have no clinical validation, and cannot override the deterministic batch/manufacturer gates. The user confirmed no existing trained artifacts and requested that these models be built.

The existing Supabase project is configured locally. Its secret values are not recorded here. The user approved the first free public deployment; no public deployment has occurred yet.
