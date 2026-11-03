# Startup, login and billing polish — 3 November 2026

Scope: front-desk offline Android counter. No authentication algorithm, schema, `synchronous=FULL`, tax/receipt arithmetic, saved sale or backup format changes. Existing unrelated workspace work is retained. Local baseline snapshot precedes the phase commits; nothing is pushed.

## Discovery / phase A checkpoint

Source confirmed the hidden form and sequential DB → logo → branding → photos → workspace → backups → access path. The existing Settings `round_rupee` option defaults off. Fractional weight quantities are **not supported** by the existing integer-portion ledger; kg-labelled products are independent fixed portions. This task preserves that contract.

Changes: immediately rendered login shell with optional pre-paint branding/theme cache; separate entry and deferred app; disabled readiness state and safely queued early form submission; retry on DB failure; post-interactive images, workspace and backup initialization; existing asset markers and full image backups retained; current-version DB initialization avoids the DDL/seed write transaction; native splash/window blue and paint-triggered hide. Native backup validation now uses a uniquely named disposable native SQLite database, leaving WASM on the browser-preview branch. The validator, source snapshot, restore, authentication and image bytes are unchanged. Scratch deletion targets only that generated database, never `restaurant` or shared backup documents. Native execution of this new adapter remains unverified.

Detailed profiling is opt-in with `?startupProfile=1` or localStorage `restaurant.startupProfile=1`. Marks cover all seven stages plus form paint and interactivity. Existing `restaurant:ready` denotes completion of deferred startup, not time to login. First paint is a two-animation-frame observation of the visible shell, not an Android launch-to-screen measurement.

Desktop production-web Chromium 149, sql.js preview, five fresh browser contexts and five locked-owner relaunches; no connected shared backup folder. Median milliseconds from navigation:

| Scenario | Before form paint | After A form paint | Before interactive | After A interactive |
| --- | ---: | ---: | ---: | ---: |
| Empty browser storage | 740.0 | 129.5 | 720.5 | 222.0 |
| Locked-owner relaunch | 196.4 | 57.0 | 169.0 | 85.4 |

Raw stage timelines: `test-results/startup-polish/before.json`, `after-a-verified.json`; repeat with `node --import ./scripts/project-environment.mjs scripts/profile-restaurant-startup.mjs LABEL` after building. These are **not** Android debug/release or TVS results, and do not establish the requested TVS targets.

Phase A checks: 89 restaurant Node tests passed (85 baseline + two initialization + two native-adapter contract checks); seven focused Playwright scenarios passed, including delayed DB/early submit, DB failure/retry, nonblocking photo work, cached-name/removal priority, owner login, old-schema migration and full-image backup/restore. Lint and production web build passed. Native build result and final all-phase checks are recorded below when available. Actual TVS, fresh APK install, release timings, native scratch-validation lifecycle, shared-folder provider/reinstall and physical printing remain unverified. Connected OnePlus Pad Go live data was not touched. ABI narrowing (A10) intentionally omitted; it is optional and ABI support on TVS has not been measured.

Vite reports the intentional copied classic scripts (needed before module execution), existing duplicate icon import and lazy Excel chunk size warning. No external fonts or runtime network dependency was added.

Phase A wider browser run initially had 40 passes / four failures: deferred base CSS changed tile/cart geometry, and icons rendered before registration. Eagerly loading the shared base stylesheet before restaurant overrides and registering both icon sets before preferences corrected these. All eight affected/startup scenarios passed on the corrected build. Android debug assemble/lint succeeded (0 errors, 19 existing warnings); 11 unchanged Java tests passed using Gradle cached results. This does not verify the native JavaScript adapter or splash on hardware.

## Phase B checkpoint

Changed login markup, access presentation, dictionary and workspace CSS. Added a real 44px password button with bilingual eye/eye-off labels and preserved selection/value; Sign in loading/error/focus presentation; empty usernames (no new storage and no stored-account prefill); left-aligned recovery controls, 14px helper/credit text, white padded badge and smaller brand/headline gap. Offline note now reads “Works offline. Your data is saved on this device.” English headline and Software by VGL / Build · Automate · Grow wording remain. Authentication derivation, lockout and recovery rules are unchanged.

Verified: ten login/startup/branding browser scenarios passed; after visual QA caught the inherited dark-blue recovery-link color in dark mode, an explicit theme-token color was added and all five new login cases passed again. Checks cover 1920×1080, 1070×716, 800×1280 and 390×844, Tamil in both themes, horizontal overflow, alignment, 44px toggle, helper/credit/recovery-link contrast ≥4.5:1, focus ring, selection preservation, wrong password, busy state, Enter from both fields and empty username after lock. Web build, JS lint and classic-script syntax checks passed. Screenshots are local under `test-results/startup-polish/login-*`. On short screens first-owner setup can scroll vertically; no fields are clipped. Native touch/keyboard/TVS appearance is unverified.

## Phase C checkpoint

Quantity input strips only a trailing zero fraction for display; stored draft values remain unchanged. “Standard” is hidden for singleton dishes and retained if another active portion of that name/category exists. Explicit parcel/half/quarter labels remain. The breakdown defaults closed and expands in one column, ordered Gross, Discount, Taxable, CGST, SGST, Round off, then the permanently visible Total. Total/Pay stay in the cart on desktop and in a fixed footer on narrow layouts. Short landscape uses a compact Total/Pay row so cart actions remain reachable. Clear uses a touch-friendly existing-style modal and retains Cancel/Undo. Hold/Recall and checkout validation are unchanged. Sidebar names use available full width (at widths where the existing sidebar shows names); compact navigation still uses its original collapsed branding. The apparent “Tax invoice button” was a noninteractive span: it now explicitly says “Receipt: Tax invoice” and has status semantics, with no invoice logic/toggle added. The existing “Menu prices + GST” label and configured rate labels were verified without hardcoding a rate.

Before **and** after Phase C, the same browser test passed through payment, saved and print/reprint receipt HTML, Sales/Reports, complete backup validation, and actual browser restore followed by exact table/image comparison:

| Cart / setting | Gross | Discount | Taxable | CGST | SGST | Round | Total, before = after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Egg porial ₹50 + boiled egg ₹15 + kudal gravy ₹200 + empty biryani ₹140 | 405.00 | 0.00 | 405.00 | 10.12 | 10.13 | 0.00 | 425.25 |
| Same, ₹20 bill discount | 405.00 | 20.00 | 385.00 | 9.61 | 9.64 | 0.00 | 404.25 |
| Existing chicken biryani 1/2 kg fixed portion | 160.00 | 0.00 | 160.00 | 4.00 | 4.00 | 0.00 | 168.00 |
| Required cart, existing rounding ON | 405.00 | 0.00 | 405.00 | 10.12 | 10.13 | -0.25 | 425.00 |

Four saved bills/payments and report totals reconcile to ₹1,422.50. The discount GST split preserves the existing **per-line** allocations. Receipt calculations/templates and accounting functions were not changed. Browser printing is HTML/print-dialog verification, not physical paper verification. True fractional-weight `0.500 kg` checkout remains unsupported by the preexisting schema/business contract and was intentionally not added.

Focused C checks: seven existing regression/hold/migration/touch scenarios passed; all eight billing regression/polish cases passed after correcting short-landscape footer geometry (and a test locator that matched quantity buttons as well as tiles). New layout checks cover 1920×1080, 1280×720, 1070×716, 800×1280, 390×844 and 732×336; Tamil/dark mode preserves totals, summary order and modal labels. 89 Node tests passed. A disposable OPFS folder-provider test also passed with backup writes deliberately stalled: login completed while the first full backup remained pending, then the saved backup contained 23 images, 36 photo references, owner account and install markers. This emulates a provider; it does not verify native SAF/reinstall survival.

## File changes by phase

These are task changes relative to the preserved local baseline, not all preexisting uncommitted work in this independent clone.

| Phase | File | Purpose |
| --- | --- | --- |
| A | `restaurant/entry.js` | Paint shell/preferences first, gate early submissions, hide native splash, catch startup failure. |
| A | `restaurant/app.js` | Separate DB/access readiness from deferred workspace/assets/backups; refresh/cache branding. |
| A | `restaurant/index.html` | Visible form, safe initial disabled controls, status/Retry and pre-paint script hooks. |
| A | `restaurant/public/login-branding.js` | Apply optional cached identity/theme synchronously; local bundled identity fallback. |
| A | `restaurant/public/startup-profile.js` | Opt-in stage diagnostics. |
| A | `restaurant/original-billing-template.js` | Inject escaped default name from existing configured defaults. |
| A | `restaurant/access-ui.js` | Preserve early typed credentials and initialize access independently of optional work. |
| A | `restaurant/repository.js` | Read-only fast path for already initialized schema/setup revisions; preserve existing migration/seed path. |
| A | `restaurant/drivers.js` | Native scratch validation adapter, failed-open cleanup; WASM only on browser branch. |
| A | `restaurant/preferences.js` | Bilingual readiness/error/background messages. |
| A | `capacitor.config.json`, `android/app/src/main/res/values/styles.xml` | Blue native window/splash and paint-triggered hide configuration. |
| A | `package.json`, `package-lock.json` | Pin `@capacitor/splash-screen` 8.0.2. Earlier dependency setup was separately snapshotted. |
| A | `android/capacitor.settings.gradle`, `android/app/capacitor.build.gradle` | Generated native plugin inclusion, including splash. |
| A | `scripts/profile-restaurant-startup.mjs` | Repeatable five-context/five-relaunch desktop measurement. |
| A | `tests/restaurant/startup.test.js` | No-write warm open and newer-schema rejection. |
| A | `tests/restaurant/native-validation.test.js` | Real disposable SQLite through a mock native bridge contract; verify temporary/live cleanup boundaries. |
| A | `tests/restaurant-browser/startup.spec.js` | Delayed DB, queued submit, Retry, optional images and cached branding. Final verification adds stalled-folder backup coverage. |
| B | `restaurant/index.html` | Password toggle markup and new offline note. |
| B | `restaurant/access-ui.js` | Eye/eye-off, selection preservation, empty username, localized busy/errors. |
| B | `restaurant/preferences.js` | Login dictionaries, labels, placeholders and headline/subtext translation. |
| B | `restaurant/workspace-style.css` | Login badge/spacing, 14px helpers, contrast, alignment and focus/error states. |
| B | `tests/restaurant-browser/login-polish.spec.js` | Cursor/loading/Enter plus four responsive contrast/focus cases. |
| B | `tests/restaurant-browser/workspace-upgrade.spec.js` | Existing login test now enters the deliberately empty username after locking. |
| C | `src/vglpos/web/static/src/js/pos.js` | Count/portion display and clear-confirm interaction only. |
| C | `src/vglpos/web/templates/pos.html` | Collapsible breakdown, visible checkout footer and confirmation dialog. |
| C | `restaurant/style.css` | Single-column totals, pinned/compact footer and two-line visible sidebar identity. |
| C | `restaurant/app.js`, `restaurant/preferences.js` | Read-only receipt-type status and bilingual breakdown/confirmation strings. |
| C | `tests/restaurant-browser/billing-polish-regression.spec.js` | Same four financial scenarios before/after, saved/printed output and exact backup/restore reconciliation. |
| C | `tests/restaurant-browser/billing-polish.spec.js` | Quantity/portion/confirmation/Undo and six responsive bilingual layouts. |
| C | `tests/restaurant-browser/converted-billing.spec.js`, `receipt-performance.spec.js`, `restaurant.spec.js` | Update only assertions for intentionally changed quantity/status display; retain numerical checks. |
| Final checks | `tests/restaurant-browser/access-helper.js` | Fixture waits for DB readiness before deciding whether confirmation is required. |
| Final checks | `tests/restaurant-browser/recovery-polish.spec.js` | Existing backup link, simulated folder reconnect, wrong/correct saved-owner authentication and restored sale. |
| A/B/C | This report | Discovery, checkpoints, evidence, limitations and final checklist. |

The source logo JPEG, all menu-photo files/manifests/one-time installers, `access.js`, `schema.js`, `domain.js`, `backup.js`, `backup-service.js`, `backup-folder.js`, `documents.js` and image store are unchanged from the baseline. No private reference files, live device data or credentials were modified or uploaded. No publication/push occurred.

## Requirements checklist

“Verified” below means source plus the stated desktop/automated evidence. It does **not** mean the APK/TVS hardware has passed. Physical-device limitations apply to all rows.

| Item | Status | Evidence / limit |
| --- | --- | --- |
| A1 | Implemented but not verified | All stage/paint/interactive marks exist; measured browser fresh/relaunch. Actual install/relaunch Android debug/release/TVS baseline unavailable. |
| A2 | Verified | Visible form before delayed DB; disabled readiness and queued early submit; double-submit guards retained. |
| A3 | Verified | Optional image/workspace/backup stages follow access readiness; stalled image and folder-write cases allow login. Native provider pending. |
| A4 | Verified | Synchronous optional name/logo cache, DB refresh, name edit/logo removal survives restart. Native first-frame observation pending. |
| A5 | Verified | Current-version warm open uses no write transaction; fresh seeding and legacy migration tests pass. No new schema/seed content introduced. |
| A6 | Implemented but not verified | Build splits app/reports/backup/Excel/ZIP; preview-only WASM branch and native scratch adapter contract verified. Actual native validation execution pending. Printing bridge is invoked on demand; lightweight receipt helpers remain in the deferred app chunk. |
| A7 | Implemented but not verified | Native backgrounds and paint-triggered hide compile in both variants. Actual launch/rotation/flash behavior pending. |
| A8 | Verified | Browser DB failure displays actionable Retry and recovers without clearing data. Native fault injection pending. |
| A9 | Not done | No actual TVS debug/release before/after timings. Desktop comparisons are diagnostic only. |
| A10 | Not done | Optional ABI filter deliberately omitted; exact TVS ABI support is not established. |
| B1 | Verified | Real button, 44px target, English/Tamil aria labels, value and selection preserved. |
| B2 | Verified | Recovery label/link share field left edge at four sizes. |
| B3 | Verified | Helpers/credit/link ≥13–14px and contrast ≥4.5:1 in both themes. |
| B4 | Verified | New offline sentence in both dictionaries. Recovery behavior retained and browser-tested. |
| B5 | Verified | No new username storage; no account-name prefill; existing autocomplete retained. |
| B6 | Verified | Cached original image in padded white badge; JPEG unchanged. |
| B7 | Verified | Smaller logo/headline gap; original English headline/subtext and VGL credit/tagline retained. Screenshots inspected. |
| B8 | Verified | Inline wrong-credential error, disabled loading, readiness, Enter from both fields, visible focus. |
| C1 | Verified | Whole **portion counts** displayed as integers; stored quantities unchanged. True fractional-weight sale/test not done because this ledger has no weight-selling model. |
| C2 | Verified | Existing Settings option defaults off; ON/OFF screen/saved/receipt/report/restore agreement tested. |
| C3 | Verified | Expanded breakdown order and right-column alignment checked; arithmetic unchanged. |
| C4 | Verified | Default collapsed; Total/Pay in viewport across six simulated sizes, including short landscape. Real TVS pending. |
| C5 | Verified | Existing menu-price-basis label and rate labels derive from current settings, no hardcoded new tax rate. |
| C6 | Verified | Singleton Standard hidden; adding a second same-name portion restores its label. Explicit portions retained. |
| C7 | Verified | Visible sidebar name is at most two lines on tested wide layouts. Original compact sidebar/bottom navigation still hides the brand name by design. |
| C8 | Verified | Modal confirmation, cancel, confirm and existing Undo; Hold/Recall regressions pass. |
| C9 | Verified | Read-only configured receipt status is explicit; no invoice logic change. |

## Deliberately unverified / unchanged

- Actual TVS Android 11 timing, RAM/storage/endurance, USB reconnect and physical receipt output; native splash first-frame behavior; exact physical font matching.
- Fresh APK install, real uninstall/reinstall and SAF permission reacquisition/provider lifecycle. Browser fresh/reconnected-folder recovery and saved-owner authentication were tested in disposable storage only.
- New native scratch adapter execution/performance on the TVS (or any physical device). Node bridge-contract tests exercise the same adapter against real SQLite, not SQLCipher/Android IPC. Large-history backup validation performance needs device measurement.
- Release runtime timing/signing/installation: the built release APK is **unsigned**, not a deployment-ready release. Both artifacts retain existing version 1.0.17 (18); no live update was installed.
- True weighted `0.500 kg` billing would require separately authorized business/schema work. Existing 1 kg/half-kg independently priced portions remain unchanged.
- Historical bill snapshots, GST/rounding/receipt arithmetic, append-only backup documents, account derivation/lockout and all photos were intentionally preserved. The 13 previously reported moderate dependency vulnerabilities were not addressed by unrelated upgrades.
- Branding note: the logo says **“Arafa”**, while the app name says **“Arafah”**. The logo was not edited.

## Final verification and measurements

Final source review moved the password eye binding into the early entry, so it works and is localized while DB opening is deliberately stalled. That final display-only initialization is idempotent and preserves an early visibility choice. Eleven focused startup/login/branding cases passed, followed by the complete final browser run. The copied classic profiler avoids newer logical-assignment syntax, and the breakdown has a vh fallback for WebViews without dvh support.

| Check | Actual result |
| --- | --- |
| `npm test` | 100 passed (89 restaurant + 11 existing frontend/tax checks); legacy build also passed. |
| `npm run test:restaurant:browser` | Final run: **59 passed**, 4.7 minutes. |
| `npm run lint:js` | Passed, zero warnings. |
| `npm run build:restaurant` | Passed; intentional classic-script copy and lazy Excel chunk-size warnings remain. |
| Classic early scripts | `node --check` passed for both. |
| Separate type checker | Not configured for this vanilla-JS app; no TypeScript type-check pass is claimed. |
| Android debug | Assemble + lint passed, 0 errors / 19 preexisting warnings. 11 unchanged Java tests reused cached passing results. |
| Android release | Assemble and its vital-lint tasks passed; output is unsigned. No release installation/timing was performed. |
| Scoped Semgrep | 54 tracked runtime files, four configured rules, zero findings. |
| APK contents/signature | All 67 web files match in both variants; the two generated Cordova bridge files also match. Debug APK v2 signature verifies. |
| Protected source comparison | No task diff in authentication algorithm, schema, money/tax/receipt calculations, backup validator/restore/transport/service, photo installers/manifests/assets or image store. |

Earlier full runs exposed stale display assertions and fixture races: the helper now waits for DB readiness before deciding whether owner confirmation is needed; the stalled-photo branding test now expects the intentionally enabled login; quantity/status assertions follow the requested display; the slow-backup test waits for the appended owner-account snapshot instead of assuming a pre-account photo snapshot already contains credentials. The final full run includes all corrections and has no failures.

### Final desktop before/after (navigation-relative milliseconds)

Five fresh contexts and five locked-owner relaunches, production Vite web build, Chromium 149, sql.js preview, original 36-product/23-image setup and no selected folder. Same harness/marks as baseline. These samples do not include Android process/launcher startup and do not characterize TVS storage or CPU. All raw samples, not only medians, are retained in `test-results/startup-polish/before.json` and `final-verified.json`.

| Scenario | Before form paint | Final form paint | Before interactive | Final interactive |
| --- | ---: | ---: | ---: | ---: |
| Empty browser storage | 740.0 | 175.1 | 720.5 | 350.4 |
| Locked-owner relaunch | 196.4 | 62.6 | 169.0 | 108.2 |

Stage table below shows independently calculated median start/end marks in ms, not additive durations; deferred stages can overlap. In the final entry, translation/preferences run before the DB-core mark and before form paint; the original core span also included label initialization. Overall navigation-to-paint/interactive comparisons above include both paths in full.

| Stage | Fresh before start/end | Fresh final start/end | Relaunch before start/end | Relaunch final start/end |
| --- | ---: | ---: | ---: | ---: |
| 1. Core DB/seed | 131.9 / 290.6 | 193.9 / 337.8 | 39.8 / 88.5 | 78.0 / 103.4 |
| 2. Logo install guard | 291.1 / 327.0 | 377.6 / 476.1 | 88.7 / 92.1 | 136.6 / 173.1 |
| 3. DB branding refresh | 327.0 / 332.7 | 476.1 / 480.4 | 92.1 / 96.2 | 173.1 / 178.6 |
| 4. Photo install guards | 332.8 / 651.5 | 480.4 / 740.1 | 96.2 / 103.8 | 178.6 / 189.3 |
| 5. Workspace setup | 651.5 / 704.5 | 359.1 / 458.8 | 103.8 / 146.3 | 111.2 / 178.1 |
| 6. Backup setup/write | 704.5 / 707.5 | 756.7 / 782.0 | 146.3 / 157.3 | 189.3 / 197.9 |
| 7. Access setup | 708.4 / 720.5 | 337.9 / 350.4 | 157.7 / 169.0 | 103.4 / 108.2 |

### Requested Android/TVS debug and release timing comparison

| Variant | Scenario | Before | After | Reason |
| --- | --- | --- | --- | --- |
| Android debug / TVS | First launch after install/update | Not measured | Not measured | TVS unavailable; no live-device install or data reset performed. |
| Android debug / TVS | Normal relaunch | Not measured | Not measured | Same; browser numbers are not substituted. |
| Android release / TVS | First launch after install/update | Not measured | Not measured | TVS unavailable; release artifact is unsigned and was not installed. |
| Android release / TVS | Normal relaunch | Not measured | Not measured | Same. |

The requested TVS <~1s relaunch / <~2s first-launch targets remain **unverified**. OnePlus Pad Go was detected by ADB but its live app/data were not touched; no speed claim is made for it either.

### Artifacts retained locally

Both packages remain version **1.0.17 (18)**. Artifact paths below are new task outputs, not installation records. `test-results/startup-polish/apk-verification.json` contains byte counts and asset verification; `debug-signature.txt` contains signature output. The local verification utility is `.tools/verify-polish-artifacts.mjs`.

- `D:/vgl-restaurant-pos/artifacts/restaurant-pos-startup-polish-debug.apk` (16411956 bytes), SHA-256 `fce41f78ef1cadd5c0f2e30e3ca0a76db2a14ddf9ea21e2ce17e3fc89eadc804`.
- `D:/vgl-restaurant-pos/artifacts/restaurant-pos-startup-polish-release-unsigned.apk` (14536269 bytes), SHA-256 `c4034566441bfb1b4d4d41383cb716b9a0e2486ec5fde007a5a8c31f34d5eccc`.

Phase commits: A `b0caee2`; B `2cac5dc`; C is the separate billing/final-verification commit containing this report. Baseline snapshots `45f27b8` and `794bf49` preserve the preexisting restaurant code/dependencies. Earlier unrelated modifications/untracked project files remain in the workspace. No push, publication, device installation, live restore or owner-data mutation occurred.

