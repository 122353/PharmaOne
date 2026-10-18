# Final manual acceptance checklist

> Historical BYOK-era checklist. Use the [current final testing checklist](FINAL_TESTING_CHECKLIST.md).

Use only synthetic pharmacy names and stock. Restart both servers after the latest code changes.

1. Open `http://localhost:3000/`; confirm the landing page works on desktop and phone width.
2. Sign up with a disposable confirmed Supabase account, sign out, sign in, refresh, and confirm the session remains valid. Check that an expired or invalid session returns to sign-in.
3. Complete pharmacy onboarding and save a profile. Refresh Settings and confirm the profile remains.
4. If the verified August 2026 source snapshot is not visible, run `python -m app.verified_snapshot` from `D:\PharmaOne\api`. This imports previously verified records without a TinyFish charge.
5. Upload [`demo/synthetic-stock.csv`](../demo/synthetic-stock.csv). Confirm one Linezolid batch is a potential match, the missing-manufacturer row needs verification, and wrong batch/strength rows are not treated as confirmed matches. Upload the same file again and confirm duplicates are skipped.
6. Open the matched alert. Check medicine, manufacturer, batch, quality finding, reporting period, retrieved time, and official CDSCO link. The source link opens a filtered database, not an individual record URL.
7. Add a pharmacist note, mark reviewed, simulate a hold, refresh, and reopen from Investigations. Confirm the timeline and simulated status persist. Confirm no real stock restriction is claimed.
8. With a second confirmed account, create another pharmacy. Confirm it cannot see or change the first pharmacy's inventory, investigations, profile, or TinyFish connection. Public CDSCO records may be shared.
9. If you choose to spend a TinyFish credit, connect your own key in Settings, explicitly select a reporting period and click sync once. Confirm its run status, retrieved records, source URL, and timestamp. Check that the key is masked and disconnect works. Do not call this step passed until an actual run succeeds.
10. On a phone-sized screen, check dashboard, import, alert detail, investigations, and Settings. Note any overflow or unreadable table.

If any step fails, record the route, action, expected result, actual result, and time. Do not include keys, passwords, tokens, or patient data in screenshots or logs.
