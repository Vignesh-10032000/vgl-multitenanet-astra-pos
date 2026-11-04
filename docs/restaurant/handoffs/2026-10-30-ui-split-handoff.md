# UI, dashboard and split-payment continuation — 30 October 2026

## Why this record exists

The owner asked for a handoff and a prompt to continue in a **new chat under the same project**, instead of continuing this long chat. Implementation stops at this checkpoint. No claim of task completion or production acceptance is made. Only handoff documents were updated after that request. Historical root documents were copied to `2026-10-30-pre-ui-*.md` before replacement.

Workspace: `D:\vgl-restaurant-pos`. Branch/HEAD freshly checked: `codex/restaurant-offline`, `c6e39137ed0c84b431596a6d0d237d7b2ecdb66b`. Substantial implementation is still local/untracked/uncommitted. Preserve it; do not use reset/clean or clone over it. Leave `D:\vgl pos` and the CRM untouched. No push, publication or reference uploads.

## Authorization and exact desired result

The owner originally asked for UI/labels/defaults/report-query changes without billing/schema/hardware edits. A clarification explicitly answered **“Include split payment and ledger changes now”**. Necessary schema/checkout/refund/backup/receipt/export changes are therefore authorized. Keep tax calculations, immutable snapshots, local final numbering and native print-service/hardware route intact. Scope record: `docs/restaurant/ui-split-scope-2026-10-30.md`.

- Convert/reuse the ORIGINAL dashboard source/design, as already done for the billing source. Keep HTML/CSS/vanilla JS. Screenshot style: gradient dashboard welcome banner, summary cards, panels and recent transactions. No inventory content.
- Dashboard: six bilingual summary cards, Cash/GPay split, top five items and last five bills; no full bill table or exports.
- Sales: searchable bill/customer list, dates and payment filter, View/Reprint and Cancel/Return; only one thin totals strip, no dashboard cards.
- Reports: date range, Day-wise / Item-wise / Payment-wise / Cancelled bills tabs; CSV/XLSX/PDF export only here.
- Independent defaults: payment All everywhere; Dashboard Today; Sales Today; Reports This month. Date chips: Today, Yesterday, This week, This month, Custom.
- Billing: remove Quick keys and F1–F9 strip/hints, touch Hold/Recall, categories visible, at least three preferably four usable cart rows, professional aligned customer fields (name/phone/city), no horizontal screen scroll, targets >=44px. Preserve left menu/right cart arrangement. Do not implement KOT.
- Split example: ₹150 = Cash ₹50 + GPay ₹100, recorded as cash + underlying `upi`. Cashier marking GPay is not gateway settlement. Excess cash is change. Partial mixed returns record actual returned channels; do not invent proportional refunds.
- Hide browser-preview SQLite footer on native Android.
- Verify actual Tamil appearance on screen, receipt and PDF, plus accounting: Total Sales - Cancelled = Final Sales; Cash + GPay = Final Sales. Give file-by-file evidence and separate device limitations.

Central requested labels, as two lines on cards and reused by exports:

| English | Tamil |
| --- | --- |
| Total Bills | மொத்த பில்கள் |
| Total Sales | மொத்த விற்பனை |
| Cancelled / Returned | ரத்து / திரும்பக் கொடுத்தது |
| Final Sales | இறுதி விற்பனை |
| Cash in Counter | கல்லாவில் பணம் |
| GPay Received | GPay வரவு |

Final Sales helper: `Total Sales minus Cancelled`.

GST is already owner/accountant confirmed: GSTIN **33BPFPD3960P2ZN**, included CGST 2.5% + SGST 2.5%. ₹170 remains ₹170; taxable ₹161.90 + ₹4.05 + ₹4.05. Do not re-ask or change defaults based on old composition filings. Preserve historical snapshots/settings upgrades.

## Existing work that is already real

The earlier original billing conversion is implemented IN PLACE: `src/vglpos/web/templates/pos.html` and `src/vglpos/web/static/src/js/pos.js` power the restaurant build through a Vite extraction plugin and local adapter. This is no longer just copied CSS. The new original-dashboard adaptation is also in place. Older handoffs saying original `src/` is unchanged are historical.

Useful existing SQLite drivers, integer-paise/BigInt domain logic, images, consistent backups, receipt/export services and Capacitor Android components are preserved. Never start a third controller or framework rewrite. See `original-billing-conversion.md` for the previous slice and `quality-gate-2026-10-29.md` for its older evidence.

## File-by-file current implementation

These are written changes, **not a claim that all UI behavior is verified**:

| File | Change / review focus |
| --- | --- |
| `restaurant/domain.js` | Adds validated one/two-channel payments: unique cash/upi, integer shares sum exactly to bill, cash change and exact UPI. Existing single payment and tax logic retained. |
| `restaurant/schema.js` | Schema v2: payment position/composite primary key and unique method per bill; new adjustment_payments; legacy column map and reusable payment DDL. |
| `restaurant/repository.js` | Transactional v1 migration; atomic multi-tender checkout; saved `.payments` plus compatible `.payment`; actual refund channels and idempotency; report query avoids split joins duplicating invoices/lines; selected shares and per-channel corrections; exact summary invariant; top five. Snapshot/replace methods retained (see caution below). |
| `restaurant/backup.js` | Strict v1 shape/checksum validation before upgrading backup in memory; v2 tender/return consistency; complete image/scratch-SQLite restore checks retained. |
| `restaurant/billing-adapter.js` | Controller split rows map to exact shares/tendered cash/change; single-tender request compatibility retained. |
| `src/vglpos/web/static/src/js/pos.js` | Passes bill total to split adapter; Split Cash + GPay toggle, touch Hold/Recall, customer selection export; removed quick-key/F-key functions, state, initialization and bindings. |
| `src/vglpos/web/templates/pos.html` | Removed Quick keys/grid, F-key footer/hints/help/settings dialogs; labeled Add customer, touch cart actions, split toggle; original cart/payment structure retained. |
| `src/vglpos/web/templates/dashboard.html` | Adapted original dashboard with welcome banner, six metrics, payment panel, top five and last five. No stock or export panel. |
| `src/vglpos/web/static/src/js/dashboard.js` | Adapted original renderer to report snapshots and centralized bilingual labels; no server/session/stock dependency. |
| `restaurant/original-billing-template.js` | Extracts/watches both original billing and dashboard content blocks into restaurant shell; guards residual Jinja. |
| `restaurant/labels.js` (new) | Central metric English/Tamil, helper, filter/customer/screen/payment labels; metric header and payment display helpers. |
| `restaurant/report-dates.js` (new) | Today/yesterday/Monday-week/month presets including year boundaries. |
| `restaurant/reporting-ui.js` (new) | Independent three-screen filters/defaults; dashboard renderer; thin totals strips; searchable Sales; Reports tabs and Reports-only exports; request-sequence guards. |
| `restaurant/index.html` | Separate dashboard/sales/reports sections; original-dashboard marker; professional customer form; mixed return channel fields. |
| `restaurant/app.js` | Reporting integration/routing, Add/Edit customer and billing selection, explicit mixed return inputs, native footer flag. Review routing/event registration first for browser failures. |
| `restaurant/documents.js` | Saved receipt shows each payment allocation and cash tender/change; mixed receipt merchant QR uses UPI share. Native bridge/hardware implementation unchanged. |
| `restaurant/exports.js` | Bilingual summary/daily/monthly metric labels; added Payments dataset (9 XLSX sheets now); invoice/correction channel/selected-share columns; wrapped XLSX headers. Review filtered item reconciliation before completion. |
| `restaurant/style.css` | Appended touch/billing/cart/customer/filter/dashboard/report layouts and native-footer rule; responsive checks still needed. |
| `eslint.config.js`, `package.json` | Original dashboard now included in JavaScript lint scope. Existing D:-environment preloader retained. |
| `tests/restaurant/split-payment.test.js` (new) | Split sale, retry, atomic second-payment rollback and actual refund channels. |
| `tests/restaurant/split-migration.test.js` (new) | v1 database migration/history/numbering, v1/v2 backup restore and missing tender rejection, date boundaries. |
| Existing restaurant/browser tests | Updated intentional touch controls, Sales IDs, geometry contract, nine export sheets and bilingual summary lookup. Current browser run still fails; do not interpret test edits as acceptance. |

Earlier files such as original i18n/payment-view/pos-icons, Android plugin/tests, tooling scripts, images and settings contain preserved work from the prior slice. Untracked emulator/shell helper scripts may be side-chat work; preserve them and inspect before using. Do not overwrite them as disposable.

## Fresh verification at this checkpoint

Latest runs during UI/split work:

- `npm run test:restaurant`: **35 passed**, including six new split/migration/date cases and existing money/backup tests.
- `npm run lint:js`: passed after original dashboard inclusion and removing obsolete unused quick-key code.
- `npm run build`: passed, restaurant web assets generated; existing large ExcelJS lazy-chunk warning remains. This is a web build only.
- `npm run test:restaurant:browser`: **6 passed, 7 failed**, completed in approximately 4.2 minutes. Session 45831 is finished (exit 1). Full errors/screenshots/traces retained under `test-results/restaurant-browser/`.

The original 11 frontend checks (including 200 tax-parity scenarios), current Semgrep/security scan, Android Lint/Java tests, new Android package, new desktop profile, and new Tamil PDF visual review were **not rerun after this UI/split change**. Earlier green numbers must not be presented as current.

### Exact browser failures to diagnose first

1. `converted-billing.spec.js:8`, BILL-UNDO-01: Undo toast button missing after completing/closing receipt; click timed out at line 19. Determine toast lifetime vs changed flow; retain the stale-undo protection requirement.
2. `converted-billing.spec.js:103`, repeated complete/failed print/reprint: `#print-status` stayed at initial saved message after Print; expected failure message missing at line 122. Inspect handler registration and console errors; do not assume print infrastructure broke.
3. `restaurant.spec.js:8`, GST settings/receipt/reprint: settings GSTIN input was empty at assertion; expected confirmed GSTIN. Determine routing/initialization failure before touching persisted/default GST.
4. `restaurant.spec.js:99`, cash/GPay/reload/filters: next product click blocked by still-open receipt dialog.
5. `restaurant.spec.js:135`, local photo/Tamil customer/draft: Add product remained invisible after Products navigation.
6. `restaurant.spec.js:213`, export/backup: Add customer remained invisible after Customers navigation.
7. `restaurant.spec.js:296`, older-WebView/monthly export: restore dialog remained hidden after file selection.

Passing cases covered photo tile sizing, selected-product undo regression, original quantity/undo behavior, touch hold/reload/recall, original left/right billing geometry, and phone portrait overflow. They do **not** establish new dashboard/split end-to-end acceptance. Some failures may share app initialization/routing/event causes; that is an investigation lead, not an established diagnosis.

## Resume order and remaining work

1. Read instructions and current failure traces/console. Inspect original-controller initialization vs app event binding/routing. Fix actual failures precisely and rerun affected cases, then full regression. Do not silently weaken or skip failing assertions.
2. Add end-to-end split scenario: cash ₹170, UPI ₹170, another cash ₹170 then cancel it, mixed ₹150 (cash ₹50 / UPI ₹100). Expected Total Bills 4, Total Sales ₹660, Cancelled ₹170, Final ₹490, Cash ₹220, UPI ₹270. Check saved receipt, reprint, filtered bill uniqueness, returned channels, and backup/restore. Use actual fixture product prices or create an explicit ₹150 test product.
3. Verify independent defaults/chips when navigating Dashboard/Sales/Reports; Sales search and View/Cancel/Return; reports tabs and exports only here; no full bill table on Dashboard and at most five recent rows/top items.
4. Measure 1920x1080, 1280x720 and 1024-wide layout: no horizontal screen overflow; >=3 preferably4 cart items; 44px actions; wrapped categories; aligned customer inputs. Capture actual new dashboard/billing screenshots and inspect them. Consider `vh` fallbacks before new `dvh` declarations for older Android WebView; device WebView version remains unverified.
5. Review exports: invoices have full and selected-channel shares, but item-detail and item-sales datasets may still export only full net, without their computed matched share. Ensure filtered exports reconcile without mutating original GST/snapshots or duplicating lines. Add targeted assertions.
6. Review edge cases in new payment validator (e.g. total zero with two zero rows); controller split zero-share normalization; partial return audit/idempotency. Existing unit evidence does not replace missing browser coverage.
7. Remove any remaining barcode hint in original empty-cart translation if inappropriate. Central labels exist, but inspect remaining hardcoded UI text for requested consistency. Apply Cancel/Return wording consistently.
8. Verify Tamil appearance using real browser screenshots, saved receipt and raster PDF. PDF skill was being considered; no new PDF visual verification was completed. Physical printer glyph/font/QR correctness still requires device tests.
9. Run required complete checks: `npm test` (original + restaurant), `npm run lint:js`, targeted security scan, restaurant build and all browser cases. **npm test invokes build:legacy, which empties dist**; rebuild restaurant afterwards before Playwright/Capacitor sync.
10. Run appropriate Android Lint/Java tests and package only once UI/browser failures are resolved. Preserve older APKs; consider a new versionCode/versionName after inspecting current Gradle configuration. Record fresh hash/signature/bundled asset match. Never equate compile with acceptance.
11. Update fresh file-by-file verification report, current docs and build record; separate device limitations from passing desktop/build checks. Keep KOT and direct USB work excluded unless later evidence justifies them.

### Important implementation caution

A broad replacement during report refactoring initially removed `snapshot()` and `replace()` from repository.js. Tests detected this immediately. Both methods were restored: transactional SELECT per TABLES, reverse-order delete and forward-order insert plus foreign-key check. The latest 35 tests pass after restoration. Preserve those methods and use targeted edits to avoid repeating the mistake.

## Tools, storage and local preview

- Installed skills already used/reviewed in the task: engineering-quality-gate, Capacitor development/plugin, android-cli, testing-setup. Focused additional skill reviews are in `.tools/skill-review`: systematic-debugging, verification-before-completion, memory-leak-debugging and android-profiler. They are not automatically globally installed.
- Serena manual was read and project activated earlier; initialize your own new session. Use targeted dependency tracing. Context7/Capacitor MCP provide current APIs; they are development tools, not offline runtime dependencies.
- Hosted Chrome DevTools MCP could not reach local Windows localhost previously; local CDP through Playwright worked in `scripts/profile-restaurant.mjs`. Prior desktop measurements are only a previous baseline. New code needs fresh measurements; physical TVS data requires the TVS.
- Use `scripts/project-environment.mjs` via npm commands: temp, npm/Gradle/browser/SDK caches are on D:. `.npmrc` points to D:. Android SDK `.tools/android-sdk`, user data `.tools/android-user`, Playwright `.tools/playwright`, temp `.tools/tmp`. Old C: locations are compatibility junctions. About 2.33 GB was moved with hash verification; see `storage-migration.json`. Do not widen relocation beyond POS tools/caches.
- `npm run dev`: http://127.0.0.1:5174/#billing. A server may still be running from the earlier request (session 32717 historically); inspect current ownership/response before restarting. Do not terminate unrelated processes. Browser production tests use port 5175 with one worker and managed preview server.
- Android CLI `.tools/android-cli/android.exe`; use --no-metrics and short Unix-domain temp property when needed. See existing build/emulator scripts before changes.

## Earlier artifact and device limits

Preserved previous-slice APK: `artifacts/restaurant-pos-1.0.2-debug.apk`, version 1.0.2 (3), 14,422,780 bytes; SHA-256 `c5a8c74e3979caac89a900d07babe784a9da1c9e95f5892632ec9ffce808de5e`. It does **not** include today's UI/split changes. Older `restaurant-pos-debug.apk` 1.0.1 also preserved. Oct29 evidence: 40 Node checks, 13 browser scenarios, 4 Java tests; Android Lint 0 errors/19 warnings. Those results apply to that previous source state only.

No physical TVS/phone was attached at the prior device check. Recheck current state if useful; do not assume side-chat emulator changes are absent. Native force-stop/reboot recovery, Android backup/restore/provider behavior, actual TVS startup/touch/memory/image/report measurements, and custom APK printer repeat/reconnect/paper-out tests remain unverified. Established TVS USB -> ESC POS USB Print Service -> printer route is already proven in the field; do not repeat discovery or replace it with direct USB without demonstrated requirements. Exact receipt font/Tamil/QR physical output is not established by desktop screenshots or PDF.
