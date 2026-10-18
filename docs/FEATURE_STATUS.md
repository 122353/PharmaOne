# Feature status

## Fully implemented and tested with local or synthetic data

- Supabase JWT guarded FastAPI routes, pharmacy ownership checks, PostgreSQL persistence and direct Supabase client-role denial. Two synthetic identities passed PostgreSQL isolation tests; a real two-account Supabase session test remains open.
- CSV normalization, duplicate skipping, import history, deterministic exact-batch matching, pharmacy dashboard, investigation notes/separate review, physical and simulated-hold states, audit history, and private evidence attachments. Repeated identical actions do not add audit events.
- Central TinyFish synchronization command behavior against a mocked provider, including failure retention, bounded retry and non-overlap lock.
- Regulatory source provenance, meaningful version history, added/updated changes and pharmacy-specific impact view.
- Browser Tesseract.js OCR on a synthetic package image, raw text, manual correction and server-side identifier checks. Sarvam OCR remains an optional separately charged API path and has only mocked verification.
- PharmaMatch v1 advisory similarity and PharmaClassify v1 advisory finding category, trained locally from disclosed synthetic examples and packaged as small JSON artifacts. Synthetic holdout was 12/12 and 6/10; real-world model quality is unverified and deterministic batch/manufacturer gates control alerts.
- ContextOS evidence selection, citation and evidence-only fallback; mocked Sarvam chat, translation, OCR and provider errors.
- Private synthetic supplier routes and reference mock ERP import.
- English/Hindi language selector persisted across route changes and refresh, with translated navigation, authentication, password recovery, dashboard and key scan/ContextOS text.

## Partially implemented or unverified live

- Central TinyFish: the user confirmed a live `AUG-2026` sync; PostgreSQL contains its succeeded run and ten current alerts with source URLs and timestamps. A read-only comparison against the official CDSCO public table matched all ten by period and batch; all substantive fields matched. Two manufacturer values differ only in whitespace. See the [field-by-field report](../evidence/cdsco-live-compare-2026-10-18.json). No repeat TinyFish call was made.
- Sarvam chat: one approved live text call after prompt and validator repairs returned "Batch VRNT-933 was flagged for Dissolution." The ContextOS handler accepted it in `sarvam` mode with official CDSCO citation and a persisted `success` audit. A mocked browser ContextOS journey passed; a signed-in live browser submission remains open. Two of the three additionally authorized text calls were unused.
- Sarvam OCR and translation: keys, documented adapters and mocked tests are ready; live account behavior remains unverified and requires separate approvals.
- Browser QR/barcode camera scanning: ZXing decoded generated QR and EAN-13 fixtures; an invalid symbol was rejected and a product-only EAN left batch blank. A real camera/device and physical medicine label have not been exercised.
- Hindi interface: navigation, authentication, password recovery, dashboard and key scan/ContextOS text are translated; several legacy detail, supplier and settings pages remain English. Sarvam Hindi answer behavior is mocked only.
- ContextOS answer safety: deterministic citations and batch checks exist, but an LLM response cannot be formally proven free of every unsupported claim. Pharmacist review remains required.
- Investigation evidence: small private PNG/JPEG/PDF attachments are stored; antivirus scanning and object storage are not implemented.
- Source change detection: tracked for records observed by bounded sync; deletion from CDSCO and archive-wide coverage are not tracked.
- Docker packaging: Compose configuration and health checks parse; runtime boot is blocked by the absent Docker engine.
- Supabase email: duplicate requests and rate-limit guidance are handled in the UI, and confirmation/reset redirects are implemented. Verified custom SMTP and actual delivery remain blocked by user configuration.

## Mocked demonstration only

- Pharmacy inventory in automated browser tests and the reference ERP connector are synthetic. Supplier/distributor relationships entered in the exposure view are explicitly synthetic.
- Playwright authentication and API responses are mocked; browser tests do not prove live signup/login with Supabase.

## Not implemented

- Nationwide scheduling, full CDSCO pagination, automatic recalls, physical stock restrictions, commercial ERP integrations, Neo4j and training on a representative labelled medicine dataset.
- Full Hindi translation across all legacy views and additional Indian languages.
- Production migrations, HTTPS ingress, monitored backups and provider budget administration.

The configured database retains the earlier verified snapshot and ten current alerts from the confirmed central TinyFish run. This verification made no additional paid provider request.
