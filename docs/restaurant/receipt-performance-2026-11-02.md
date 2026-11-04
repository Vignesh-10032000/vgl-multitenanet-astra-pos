# Receipt alignment and counter performance — 2 November 2026

## Owner request

The owner confirmed the CGST/SGST rupee figures must align directly under RATE, rather than under AMOUNT. Keep ₹170 base + ₹4.25 CGST + ₹4.25 SGST = ₹178.50 and all saved ledger snapshots unchanged. The same request authorized performance optimization, governed by the TVS S6802 evidence in `tvs-performance-baseline.md`.

## Changes

- `restaurant/documents.js` and `style.css`: discount, taxable value, CGST, SGST and round-off now use a footer within the existing four-column receipt table. Labels span ITEM/QTY; values occupy RATE; AMOUNT is left empty in summary rows. This uses actual column geometry, rather than manual spaces. Long numbers may wrap inside the rate column; paper width, branding, dotted item rules, large total and saved accounting amounts are retained.
- Existing billing controller: removed the fixed 150 ms quote debounce and the first redundant cart rebuild. Each completed normal tap now renders the cart once. The controller reuses the loaded billing-settings snapshot, invalidating it on `refreshBilling`; saving setup already calls that refresh. Atomic checkout still reads settings/menu and validates final money inside the ledger transaction, and still flushes pending draft writes before saving a sale. Payment-preview input debounce, owner password security and durability/backup behavior remain unchanged.
- `restaurant/image-read-cache.js` / `assets.js`: concurrent reads of the same immutable photo path share one storage operation. Retained image data URLs use an 8 MiB least-recently-used payload budget, conservatively counted as two bytes per character. Oversized images still load and remain usable; they are not retained in this cache. Errors do not poison retries. No JPEG, upload, marker, saved image reference or backup file is modified/deleted.
- `scripts/profile-restaurant-counter.mjs` and `npm run profile:restaurant:counter -- <label>` provide a repeatable disposable 1,000-bill / 22-original-image probe. The older general profiler explicitly uses its historical inclusive fixture so its existing ₹340 assertions still apply.
- Tests: four cache checks, three new browser scenarios for preview/print-column geometry, rapid taps/current settings and exact local thumbnail reads. Receipt text assertions follow the same saved amounts across the new table markup. The logo-upload regression now waits for each actual setup-save completion before reload, correcting an exposed asynchronous test race without weakening preservation checks.

## Desktop diagnostic evidence (not TVS acceptance)

Both successful probes used Chromium 149, a disposable 1,000-bill database and 22 original food photos, 20 tap samples with 4× CPU slowdown and three unthrottled warm starts. CPU slowdown is a diagnostic only and does not reproduce TVS CPU, Android bridge or storage behavior.

| Measurement | Before | After |
| --- | ---: | ---: |
| Median tap → correct total painted | 418 ms | 245.1 ms |
| Observed p95 (20 samples) | 1,564.5 ms | 968.7 ms |
| Cart render batches per tap | 2 | 1 |
| Warm image storage reads (including logo) | 37 | 23 |
| Warm ready times | 383.7 / 311.8 / 303.2 ms | 419.3 / 337.2 / 461.8 ms |

The tap result is about 41% lower in this desktop sample. Startup speedup was NOT established: the optimized warm sample was slower and timings varied. Single post-GC JavaScript heap snapshots do not establish native memory savings or absence of leaks. The cache payload limit is an implementation bound, not an approved total-memory/TVS acceptance budget.

Raw results: `test-results/receipt-performance-2026-11-02/{baseline-counter,optimized-counter,comparison}.json`. Earlier unsuccessful disposable profiling attempts produced no accepted measurements and changed no business data.

## Verification

- VERIFIED: JavaScript lint/build and all 96 Node/frontend checks (92 retained + four cache tests).
- VERIFIED: focused receipt geometry, two-phase rapid checkout, changed GST settings, invalid discount rejection and image decode/read-count checks. Values align under RATE in preview and the generated 80 mm PDF, which was rendered and visually inspected.
- VERIFIED: Android assemble/lint passed, zero errors / 19 existing warnings. Eleven unchanged Java tests reused passing Gradle results. Scoped security scan: 51 files / four rules / zero findings.
- VERIFIED: APK v2 signature and all 58 byte-matched packaged web files. Candidate 1.0.17 (18), 16,027,779 bytes, SHA256 `5daf23a156be854b4271e917064ab78b6b4d8c23492ffef2006acb0e4c7f9fd4`.
- VERIFIED: 41 browser scenarios across the broad run and final targeted retry: 40 passed broadly; the logo test save-wait race was corrected, then the targeted logo case passed 1/1. Application source was unchanged. The final lint and diff checks pass.
- The project uses vanilla JavaScript and has no configured separate type checker. No new calculation algorithm was introduced; the existing GST/rounding/property/migration/backup tests are retained.

Screenshots/PDF: `test-results/receipt-performance-2026-11-02/receipt-gst-under-rate.png`, `receipt-gst-under-rate-80mm.pdf`, `receipt-gst-under-rate-rendered.png`.

## Device and data status

Candidate: 1.0.17 (18), database schema still v3. ADB still lists no TVS/device. NOT VERIFIED: installation, native performance/memory, native v3 lifecycle/migration, physical receipt/reconnect and actual reinstall recovery. No device app data, owner credentials, live ledger, shared backups or physical printer were accessed. Browser profiling/restores used disposable contexts only. Preserve all owner records, shared backups, original photos, the one-time installation markers and prior APKs. No push, publication or private-file upload occurred.
