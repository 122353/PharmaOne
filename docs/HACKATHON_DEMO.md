# PharmaOne four-minute hackathon demo

Use an already confirmed test pharmacy account and synthetic stock. Start both local servers from [README](../README.md). This script uses the previously completed TinyFish run; it does not trigger a new sync.

**0:00–0:35 — Login and source health.** Sign in and open the dashboard. Show the successful central `AUG-2026` run, retrieval time and link to the [official CDSCO NSQ database](https://cdscoonline.gov.in/CDSCO/viewPublicNSQDrug). Explain that the ten saved rows were checked against the official table; two manufacturer strings differ only in whitespace. Do not call an NSQ finding a recall.

**0:35–1:15 — Inventory and match.** Import a synthetic CSV row for Montelukast sodium & Levocetirizine hydrochloride Tablets IP, batch `VRNT-933`, with manufacturer as printed in the saved source row. Show the candidate and exact batch comparison. A potential match requires pharmacist and physical verification.

**1:15–1:55 — Scan and correction.** Open **Scan Medicine** and use a synthetic test QR or packaging image. Display the raw decoded/OCR text, manually correct an intentionally wrong batch, and confirm matching. Explain that product-only barcodes do not supply a batch. If live OCR is not separately approved or the provider is unavailable, use the local QR fixture and manual fields; describe the OCR path as mocked/unverified live.

**1:55–2:35 — Evidence and ContextOS.** Open the matching alert and source URL. Ask why `VRNT-933` was flagged only if a new paid chat call is separately approved. Label the response **Sarvam** only if the UI says `sarvam`; otherwise show the evidence-only explanation and reason. One earlier approved live Sarvam answer passed the handler. Without approval for a new call, show the recorded result in the [verification report](FINAL_VERIFICATION_REPORT.md) and use the official evidence view. Switch to Hindi to demonstrate locally translated navigation and key ContextOS text; do not claim full Hindi coverage or live Sarvam translation.

**2:35–3:25 — Pharmacist action.** Add a note, mark the official record reviewed, set physical verification pending, and record a simulated hold. Show separate review, physical and hold states and an evidence attachment. Refresh and reopen Investigations to show persisted note and audit events. State clearly that the hold does not restrict actual stock or dispensing.

**3:25–4:00 — Isolation and scope.** Briefly show synthetic supplier exposure and import history. If two disposable confirmed accounts are available, sign in as pharmacy B and show that A's records are absent; otherwise say live two-account acceptance remains open and cite the rollback-protected PostgreSQL isolation tests. End with the source provenance and pharmacist-review requirement.

The [verification report](FINAL_VERIFICATION_REPORT.md) and [manual checklist](FINAL_TESTING_CHECKLIST.md) distinguish live, automated, mocked and blocked steps. Keep all pharmacy inventory in the demo synthetic.
