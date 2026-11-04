# UI, reporting and split-payment verification — 30 October 2026

Continued the existing checkout at `D:\vgl-restaurant-pos`, branch `codex/restaurant-offline`. The original billing/dashboard conversion and all existing local work were retained. This report supersedes the red browser checkpoint in [the earlier handoff](handoffs/2026-10-30-ui-split-handoff.md). No push, publication or reference upload occurred.

## Verified desktop behavior

- **19/19 Playwright scenarios passed** in the full final run (49.4 seconds). All seven failures from the handoff are resolved. No assertions were removed to conceal them.
- **48/48 tests passed** with `npm test`: 11 preserved frontend checks (including 200 tax-parity fixtures) and 37 restaurant checks. After the last export-label edit, all 37 restaurant checks passed again.
- `npm run lint:js` passed with zero warnings. `npm run build` passed; the existing large lazy ExcelJS chunk warning remains. JavaScript is untyped; no standalone type-check task is configured.
- The scoped local Semgrep scan passed: four rules, 31 files, zero findings. This is a limited ruleset, not a complete security audit.
- Independent SymPy rational arithmetic confirmed ₹170 = ₹161.90 taxable + ₹4.05 CGST + ₹4.05 SGST. GSTIN remains `33BPFPD3960P2ZN`, inclusive 2.5% + 2.5%; menu prices and historical snapshots are unchanged.

### Root causes resolved

The app startup used the single-element `$` selector for `[data-label]` and then called `.forEach()`. This stopped initialization before routes, print handlers, close handlers and restore handlers were bound. The fix uses the existing multi-element `$$` helper. `APP-INIT-01` now checks successful initialization, routes, independent defaults and clean browser console/page errors.

The Undo notification intercepted Pay taps until its five-second expiry. Message surfaces now let taps through while the Undo button remains interactive and at least 44px. The original `BILL-UNDO-01` assertion passes: a stale Undo cannot bring sold items back. The monthly export test now checks 35 bills on Sales using This month, then checks exports on Reports, matching the authorized screen separation.

### Accounting and history

`SPLIT-UI-01` exercises ₹170 Cash, ₹170 GPay, another ₹170 Cash cancelled, then ₹150 split as ₹50 Cash + ₹100 GPay. Saved results: four bills, Total Sales ₹660, Cancelled ₹170, Final Sales ₹490, Cash ₹220, GPay ₹270. Cash/GPay filters include each mixed invoice and item once and use only its selected share. Reprint preserves the saved receipt and final number.

A mismatched mixed return is rejected. An actual ₹30 return with ₹10 Cash + ₹20 GPay leaves Final Sales ₹460, Cash ₹210 and GPay ₹250. Browser backup/restore retains four bills, five payment rows, two corrections and three returned-channel rows; the next bill receives number 000005. Tests also verify duplicate taps, atomic second-tender rollback, exact GST, changed retry rejection, schema-v1 migration, v1/v2 backup restore, corrupt backup rejection, zero-share normalization and rejection of two zero tenders on a zero-total bill.

Invoice, item-detail and item-sales exports all contain **Selected payment INR**. Integer-paise allocation includes bill round-off, reconciles exactly to selected sales and leaves original item/tax values intact. Returns remain separate audit entries on their recorded date; original quantities are not represented as refunded item quantities. XLSX is parsed by ExcelJS and amount cells are numeric. CSV quoting, negative amounts and formula-leading text remain covered.

### UI and visual review

- Dashboard, Sales and Reports have independent All-payment defaults; Dashboard/Sales start Today and Reports starts This month. Today, Yesterday, This week, This month and Custom chips are tested. Navigation preserves each screen's own selections.
- Original dashboard styling is retained. Its six English/Tamil metrics, Cash/GPay panel, top five items and last five bills are tested, including seven-bill data proving the five-row limits. Sales has the bill/customer search and View/Reprint/Cancel/Return; exports appear only on Reports.
- Billing retains left menu/right cart, visible wrapped categories, touch Hold/Recall and no F-key/Quick keys strip. At 1920×1080, 1280×720 and 1024×768, there is no horizontal screen overflow; at least three complete cart rows fit, and tested cart/category actions are at least 44×44px. The 1280×720 screenshot shows three complete rows and part of the fourth. Add customer is no longer clipped. Customer name/phone/city inputs are aligned and at least 44px tall. The existing 412px portrait checkout scenario passes.
- Browser-only SQLite footer is hidden by the native-platform flag. Actual Android display behavior still requires a device.
- Tamil dashboard, saved customer receipt and PDF invoice/summary pages were visually inspected. Poppler/pypdf parsed and rendered the 32-page monthly PDF; recurring page headings, wrapped labels, Tamil customer text and the ₹5,910 month-end reconciliation are visible. This does not establish a physical printer's font/glyph/QR output.

Evidence is under `test-results/restaurant-artifacts/`: `dashboard-tamil.png`, `dashboard-sales.png`, `billing-touch-1920.png`, `billing-touch-1280.png`, `billing-touch-1024.png`, `customer-touch-*.png`, `gst-receipt.png`, `tamil-receipt.png`, `split-upi.xlsx`, `split-backup.json`, `monthly-auditor.pdf`, `monthly-auditor.csv`, and Poppler page renders.

Browser offline checkout runs with networking disabled after loading local assets. Lazy export code and fonts are loaded from localhost with networking re-enabled and **zero external requests** asserted. Android's packaged assets are local, but actual offline cold startup/export is a separate native acceptance test.

### Desktop diagnostics

`npm run profile:restaurant` passed using local Chrome DevTools Protocol through Playwright. Chromium 149: ready mark 377.8ms, median tap-to-cart paint 23.6ms, p95 32.9ms (23 samples). After 20 cycles DOM nodes stayed at 2,648 and listeners at 148; heap was approximately 3.27MB after collection. A 1,000-bill Sales render took 1,548ms and Reports CSV download 654ms including automation overhead. No page errors. Evidence: `test-results/restaurant-performance/`. These measurements are desktop diagnostics, not TVS performance or proof of absence of memory leaks.

## File-by-file implementation record

The earlier handoff contains the full prior conversion map. These files constitute the completed UI/split slice; **continued** means existing implementation was retained and verified, not recreated in this chat.

| File | Result |
| --- | --- |
| `restaurant/app.js` | Startup selector fix; local routes, customers, return channels, reprint/restore binding retained; restaurant empty-cart wording. |
| `restaurant/domain.js` | Continued exact one/two-tender validation; reject a phantom two-channel zero-total bill. |
| `restaurant/schema.js` | Continued schema v2 payment positions and returned-payment audit table. |
| `restaurant/repository.js` | Continued atomic multi-tender checkout/migration/refunds, idempotency, immutable snapshots and unique filtered report queries; snapshot/replace retained. |
| `restaurant/backup.js` | Continued validated v1/v2 restore including tender/return consistency and images. |
| `restaurant/billing-adapter.js` | Continued exact controller-to-ledger tender normalization, cash change and single-tender compatibility. |
| `restaurant/report-dates.js` | Continued Kolkata date presets and boundary validation. |
| `restaurant/reporting-ui.js` | Continued independent filters/defaults, separate screens/tabs, search and Reports-only exports. |
| `restaurant/labels.js` | Central six bilingual metrics; readable export summary names and consistent Cancel/Return wording. |
| `restaurant/index.html` | Continued screen/customer form separation; central correction labels. |
| `restaurant/style.css` | Nonblocking toast with usable Undo, category width, visible Add customer, compact cart rows/header and older-WebView `vh` fallback. |
| `restaurant/documents.js` | Continued immutable multi-tender receipt and UPI-share QR behavior; native bridge route unchanged. |
| `restaurant/exports.js` | Selected-payment columns for item detail/item sales, allocation explanation and original numeric snapshots retained. |
| `restaurant/original-billing-template.js` | Continued extraction of original billing and dashboard templates into the local shell. |
| `src/vglpos/web/templates/pos.html` | Continued original touch billing and split controls; no shortcut chrome/KOT. |
| `src/vglpos/web/static/src/js/pos.js` | Continued original controller, touch Hold/Recall, split and duplicate-save protection. |
| `src/vglpos/web/templates/dashboard.html` | Continued original dashboard structure/design without inventory. |
| `src/vglpos/web/static/src/js/dashboard.js` | Continued local snapshot renderer and five-row summaries. |
| `src/vglpos/web/static/src/js/payment-view.js` | Continued labeled Cash/GPay split inputs and exact preview. |
| `src/vglpos/web/static/src/js/pos-icons.js` | Register hidden dashboard icons during initialization to avoid console warnings. |
| `tests/restaurant/split-payment.test.js` | Two additional cases for zero shares/totals and selected item export reconciliation, round-off, returns, numeric XLSX and unchanged history. |
| `tests/restaurant/split-migration.test.js` | Continued v1 migration, old/new backup and date-boundary coverage. |
| `tests/restaurant/backup-export.test.js` | Updated readable export-label assertion; formula/numeric-money protection unchanged. |
| `tests/restaurant-browser/restaurant.spec.js` | Monthly bill count checked on Sales and exports on Reports. |
| `tests/restaurant-browser/reporting-split.spec.js` | Six new scenarios: mixed ledger/return/restore, startup/defaults/console, dashboard limits and three touchscreen sizes. |
| `scripts/profile-restaurant.mjs` | Export measurement now navigates to Reports; fresh CDP profile retained. |
| `scripts/check-restaurant-security.ps1` | Include reused dashboard/UI/payment modules in scoped scan. |
| `android/app/build.gradle` | Increment debug candidate to version 1.0.3 (4); printer/hardware Java unchanged. |
| `START_HERE.md`, `HANDOFF.md`, `NEW_CHAT_PROMPT.md`, `docs/restaurant/verification.md`, `docs/restaurant/development.md`, `docs/restaurant/build-verification.json` | Current status/build evidence, with earlier records preserved. |

## Native build and remaining acceptance

**VERIFIED build:** `scripts/build-restaurant-android.ps1 -SkipWebBuild -Lint -UnitTests` completed successfully. Android Lint: **0 errors, 19 warnings**. Java tests were then explicitly rerun with `:app:testDebugUnitTest --rerun`: **5 passed, 0 failures** — four DocumentWriter checks and one existing scaffold check (the first build had reused their cached result). Printer/hardware Java code was not changed.

APK: `artifacts/restaurant-pos-1.0.3-debug.apk`, version **1.0.3 (4)**, **14,391,286 bytes**. SHA-256: `421b7d29803896779fb8c1bfd028a9bb326230325cf32e01fdbdeef23acdeddb`. Package `in.vgl.restaurant`, min API 24, target API 36. Native libraries: arm64-v8a, armeabi-v7a, x86 and x86_64; no TVS ABI is assumed. Apksigner 36.1.0 verified the v2 signature with one Android Debug signer, matching the preserved 1.0.2 signer. All **25** built web files match the APK byte for byte; only the two generated Cordova bridge files are additional public assets. Earlier APKs are preserved.

The machine-readable [build record](build-verification.json) includes per-asset hashes and the previous build records. Logs: `.tools/ui-split-android-build.log`, `.tools/ui-split-java-tests.log`, `.tools/ui-split-apk-signature.log`. No physical device/emulator is currently connected (`adb devices -l` returned an empty list). The existing development preview responds at `http://127.0.0.1:5174/#billing`.

**NOT VERIFIED on hardware:** installation; native SQLite v1 migration/process death/reboot; offline cold restart/export/fonts/images; SAF/provider backup and restore; TVS/OnePlus touch/performance; actual PrintManager → installed print service output, repeat/reconnect/paper-out; exact receipt font, Tamil/rupee on paper and merchant QR/payee. Follow [device acceptance](device-acceptance.md). The field USB/print-service route remains established and was not replaced. KOT remains excluded. This is not production acceptance.
