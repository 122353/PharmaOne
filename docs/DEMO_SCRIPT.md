# PharmaOne hackathon demo (3–5 minutes)

> Historical BYOK-era script. Use the [current hackathon demo](HACKATHON_DEMO.md).

**Preparation:** Start the API and web app using the commands in `README.md`. Sign in to a synthetic pharmacy account. Run `python -m app.verified_snapshot` from `D:\PharmaOne\api` if the five verified August 2026 records are absent. Keep [`demo/synthetic-stock.csv`](../demo/synthetic-stock.csv) ready. The source data is a previously verified TinyFish retrieval; do not describe it as a new live sync.

1. **0:00–0:40 — Problem and provenance.** On the dashboard, explain that CDSCO NSQ findings are quality signals, not automatic recalls. Open the source link and show the August 2026 period. State that the five displayed records were checked against the official database, with 30 compared fields and no mismatch in the stored verification report.
2. **0:40–1:30 — Pharmacy context and inventory.** Show the synthetic pharmacy profile, then import the synthetic CSV. Point out that rows missing a manufacturer stay in the verification queue.
3. **1:30–2:30 — Explainable match.** Open the Linezolid 600 mg alert, batch `TG261185`. Show product, manufacturer, exact normalized batch, NSQ quality finding, official source URL, and retrieval time. Explain why the wrong batch and 300 mg row are not confirmed matches.
4. **2:30–3:30 — Pharmacist action.** Write a note, mark the case reviewed, then select **Simulate hold**. State clearly that this is a recorded simulation and does not block dispensing. Refresh and reopen Investigations to show persistence.
5. **3:30–4:30 — Trust boundary.** Show Settings: each user can connect an encrypted TinyFish key, and sync requires an explicit account choice. Explain that this demo used a verified prior snapshot to avoid a paid run. If a real account is connected and you intentionally choose to spend a credit, separately demonstrate one bounded live sync and label it as live only after it succeeds.

Close with the current limits: one selected reporting period per sync, human stock verification required, and no automatic recall declaration or physical hold.
