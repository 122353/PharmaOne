# PharmaOne four-minute hackathon demo

## Prepare

Start the local API with `PHARMAONE_ENV=local` and `DATABASE_URL=sqlite:///./pharmaone_development.db`, then start the web app. Confirm that the resolved database is `D:\PharmaOne - Copy\api\pharmaone_development.db` and SQLite before using the demo. Use a synthetic pharmacy account and inventory only.

The verified snapshot reports **AUG-2026**. The local baseline has five regulatory records, three synthetic inventory rows, two exact potential matches, and two notification records. Both notifications are already acknowledged, so the notification list starts with zero unread. The source panel must say **Historical snapshot imported** and **No live source check is recorded**. Do not describe this as a live TinyFish check.

## Four-minute sequence

**0:00–0:30 — Product and source.** Explain that TinyFish retrieves public CDSCO evidence in an operator-controlled workflow. This screen is replaying a previously verified snapshot, not calling TinyFish.

**0:30–1:05 — Pharmacy-specific view.** Show the synthetic inventory count and the two candidate batch matches. Explain that PharmaOne compares a pharmacy's own batch stock with a reported batch and retains the official source URL, reporting period, and retrieval provenance.

**1:05–1:40 — Notifications.** Open the notification bell. Show the two acknowledged events, their finding, batch, and AUG-2026 period. Refresh to show that the acknowledged state persists. The browser regression uses a synthetic unread event to exercise the unread-to-read action without changing the saved local baseline.

**1:40–2:20 — Alert review.** Open a Review link. Compare the exact batch and manufacturer evidence, then open the [CDSCO public NSQ table](https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug) and explain that the reviewer must filter by period and batch because the source does not provide a stable per-row link. Emphasize that an NSQ result is not automatically a recall and that a potential match still requires pharmacist and physical-package verification.

**2:20–2:55 — Strength conflict safety.** The saved baseline does not contain a strength-conflict match, so do not claim that it does. Show the isolated synthetic regression instead:
```powershell
Set-Location 'D:\PharmaOne - Copy\api'
$env:PHARMAONE_ENV = 'local'
$env:DATABASE_URL = 'sqlite:///./pharmaone_development.db'
.\.venv\Scripts\python.exe -m pytest tests\test_verified_snapshot.py::test_verified_alert_to_synthetic_pharmacy_hold_persists_and_isolated -q
```
This test uses an in-memory SQLite database and synthetic CSV rows, including a 300mg inventory row against a 600mg CDSCO record. It checks that the candidate requires verification. The UI warning is covered by the synthetic browser test:
```powershell
Set-Location 'D:\PharmaOne - Copy\web'
npm.cmd test -- --workers=1 --grep "alert detail clearly requires review"
```
These are synthetic test demonstrations, not additional saved inventory or real CDSCO evidence.

**2:55–3:25 — Actual ML contribution.** The evaluation dataset contains 18 synthetic cases. Rules and the MiniLM-enhanced pipeline had 1.000 precision/recall/F1 on that small set; PharmaMatch-only had 0.667/0.333/0.444. MiniLM retrieved one candidate for verification and never promoted it to a potential match. The results are preliminary, not clinical or statistically representative validation. See [the full metrics and resource measurements](matching-evaluation.md).

**3:25–4:00 — Expansion and business.** Explain the next step as an operator-approved, budget-capped source check that records provenance, detects changed evidence, rematches each pharmacy's inventory, and emits only new or changed notifications. A lightweight one-shot scheduled worker or operator-triggered job is preferable to a scheduler inside a sleeping free web process. No schedule is enabled.

## Architecture

```text
CDSCO public NSQ evidence
        │
operator-controlled TinyFish retrieval ── verified historical snapshot
        │
FastAPI + SQLAlchemy ── deterministic batch/product/strength checks
        │                         └─ optional local MiniLM candidate retrieval
        ├─ pharmacy-scoped PostgreSQL in production / SQLite in this demo
        └─ provenance + versioned alerts + deduplicated notifications
                                  │
Next.js + Supabase Auth ─────────┴─ pharmacist review and acknowledgement
```

Supabase JWTs are verified by the API. The API scopes inventory and notifications to the authenticated pharmacy. The frontend never receives provider credentials. The production schema migration is prepared but was not run.

## Differentiation and business model

**Positioning:** PharmaOne connects public batch-level regulatory evidence to a pharmacy's own inventory and explains why a row is a candidate or needs verification. Its focus is the evidence-to-pharmacist workflow, including provenance and acknowledgement. This is a product positioning statement, not a validated survey of every competitor.

**Revenue hypothesis:** charge per pharmacy location for monitoring and workflow, with chain-level plans for multi-site administration and optional one-time ERP/import onboarding. Pricing, willingness to pay, and retention have not been validated. Do not sell pharmacy inventory or patient data.

**Nationwide expansion:** improve source coverage and revision detection, add tested inventory integrations, and support pharmacy groups while preserving tenant boundaries. Measure coverage by source period and record provenance rather than implying complete national coverage.

## Guardrails

- No live TinyFish or Sarvam request is needed for this demo.
- Historical August 2026 evidence is labeled with its period.
- No claim says an NSQ report is a recall.
- No match result establishes that stock is safe.
- Simulated holds do not restrict real stock or dispensing.
- Use synthetic pharmacy inventory only.
