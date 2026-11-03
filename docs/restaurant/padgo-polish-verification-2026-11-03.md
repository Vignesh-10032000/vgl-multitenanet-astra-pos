# Current result — 1.0.18 installed and signed-in checks completed

On the owner's resumed request, production **1.0.18 (19)** was installed on the Pad Go, the owner signed in privately, and Billing was left open in English/light mode with an empty cart. All nine original bills / 25 lines / ten payments and every original business/account/settings row remain unchanged. No assistant test sale was created in the live app. All 23 image files were preserved; all 36 menu tiles decoded. All 15 shared backups were checked unchanged after startup. The withdrawn build must not be reinstalled. Remaining acceptance limits and the earlier recovery incident are documented below.

---

# Pad Go verification and safe pause — 3 November 2026

The owner explicitly requested a safe pause, then requested continuation. The pause has been lifted; the history and safety constraints below remain applicable. No work was pushed or published. Source fixes remain uncommitted; preserve the existing dirty workspace and unrelated files.

## Last verified live-device state

- OnePlus Pad Go OPD2305, Android 14. This is not TVS performance acceptance.
- Real package: `in.vgl.restaurant`. Its previous known APK, version 1.0.17 (18), was reinstalled in place after recovery; APK SHA-256 `5daf23a156be854b4271e917064ab78b6b4d8c23492ffef2006acb0e4c7f9fd4`.
- Recovered owner ledger: **9 sales, 25 sale lines, 10 payments, 2 customers, 36 products**. All captured owner tables matched exactly, including settings/account records; integrity and foreign-key checks passed. All 23 image files were preserved. The ninth bill was created by the owner during private sign-in, not by the assistant's unpaid tests.
- Recovered closed database SHA-256: `b4bfa1ba112242d95b654d965a371493fb49a26f3f674ea1d5f327883e05521b`.
- All 14 original shared backup documents remain; the owner's ninth bill appended a fifteenth. None were deleted.
- The real app was stopped after recovery/rollback. Separate native test package `in.vgl.restaurant.polishcheck` remains installed with synthetic data only. Do not use that test app for real sales.
- At pause, ADB had no devices; reconnect to `172.20.10.9:44913` was refused and mDNS discovered none. Therefore current screen, process state, rotation restoration and a new live database checksum could NOT be verified at pause. Do not describe those as freshly verified.
- No fixed production 1.0.18 APK has been installed on the live package.

## Critical withdrawn build and recovery

The first startup-polish APK, SHA-256 `fce41f78ef1cadd5c0f2e30e3ca0a76db2a14ddf9ea21e2ce17e3fc89eadc804`, is **WITHDRAWN**. During physical-device inspection of a synthetic backup through the newly introduced native scratch-validation path, the live database changed to the synthetic one-sale ledger before restore confirmation. The lower-level cause has not been conclusively localized. Do not claim the SQLite plugin itself was proven faulty.

The app was stopped, failure evidence archived, and the nine-bill ledger recovered from the verified latest owner shared backup. Recovery was compared against the exact pre-test nine-bill snapshot, not just aggregate totals. The unsafe APK and unsigned release are retained locally under `artifacts/restaurant-pos-1.0.17-polish-WITHDRAWN-*`; never reinstall them. Earlier optimistic native-validation statements in the startup-polish report are superseded by this report.

Private evidence root: `D:\vgl-restaurant-pos\test-results\padgo-polish-2026-11-03-1793674858462`. Includes the previous installed APK, original/failure/recovered closed archives, the exact owner table snapshot, latest complete owner backup and verification JSON. These files contain private data: do not commit, upload, publish or delete them. Do not rerun recovery scripts against the already recovered owner ledger.

## Uncommitted corrective changes

- `restaurant/app.js`: all three backup inspection/restore-validation factories again use the previous isolated in-memory `browserDatabase()` validator.
- `restaurant/drivers.js`: native validation requests fail before creating a connection; normal billing uses only the native `restaurant` database. Removed the introduced native scratch database path.
- `android/app/build.gradle`: production application ID restored to `in.vgl.restaurant`, version 1.0.18 (19). Sandbox-build script temporarily changed it and restored original bytes in `finally`.
- `tests/restaurant/native-validation.test.js`: fail-closed native validation regression coverage.
- `tests/restaurant-browser/backup-inspection-isolation.spec.js`: different-ledger inspection/cancel under a native-platform flag preserves persisted ledger bytes and last receipt.
- Startup/handoff documentation warns about the withdrawn build and recovered ledger.

Safety tradeoff: sql.js/WASM is again lazy-loaded for isolated backup validation on Android as in the previous implementation. Native SQLite remains the durable source of truth. **A6's strict browser-preview-only WASM requirement is not fulfilled.** Do not silently reintroduce native scratch validation to claim A6 completion.

## Verification recorded before pause

- Corrected source: 89 Node tests passed; lint and Vite build passed.
- Three focused browser scenarios passed, including inspection isolation, billing regression and backup recovery.
- Full browser rerun was interrupted: the log records 46 completed passing scenarios, with no final suite summary. Do not claim all 60 passed. The chained final lint command was not reached; earlier standalone lint did pass.
- Production Android debug build, Android lint/unit-test build invocation, and release assembly log end in success. Debug candidate exists at `artifacts/restaurant-pos-1.0.18-debug.apk`. Final packaged-artifact/signature/assets review is pending. Release is unsigned and is not approved for distribution.
- Separate native sandbox passed seven recorded checks: first owner setup, two synthetic sales, different-ledger/full-image inspection and cancel preserving every table, reprint staying on original latest sale, corrupt-checksum rejection preserving every table, explicit confirmed full-image restore, and synthetic native checkout with WebView network emulation offline. Owner database checksum stayed unchanged. Network emulation is not a radios-off restart test.
- Sandbox restart/orientation script was interrupted. Its result file was not produced, so restart and orientation checks are **not verified**. It uses a `finally` block to restore rotation, but process interruption may bypass it. Original device settings recorded before these checks were `accelerometer_rotation=1`, `user_rotation=0`; verify actual owner preference before changing them on resume.
- Earlier unpaid native billing checks on the withdrawn build: gross 405.00, taxable 405.00, CGST 10.12, SGST 10.13, round-off 0.00, total 425.25. With 20.00 bill discount: total 404.25, CGST 9.61 and SGST 9.64. Hold/recall, cancelled clear/payment preview, Tamil/dark and image decoding were checked. These are historical checks, not final acceptance of corrected production 1.0.18.

Logs remain under `test-results/padgo-*.log`; sandbox results are `isolated-validation-results.json` in the private evidence root. At pause, no owned Node test runners or Gradle wrapper processes were running. Editor/MCP language servers were left alone.

## Resume safely

1. Reconnect wireless debugging; inspect device screen/state and rotation. Close the disposable test app. Check the recovered owner ledger without overwriting or restoring it. If the owner has used the app since pause, preserve all newer bills and take a new consistent safety snapshot.
2. Read this report and the critical warnings in START_HERE/HANDOFF before any installation. Confirm package/signature/version and all packaged assets on the production 1.0.18 candidate. Never copy a sandbox build to a live artifact alias.
3. Finish cancelled browser/native lifecycle/layout verification in the separate package. No synthetic paid bills or test restores against the real ledger.
4. Only after corrective verification, perform the already requested in-place production update with a consistent safety archive and exact before/after data comparison. Let the owner sign in privately; never request their password.
5. Complete the user's phase checklists, actual debug/release startup measurements and final report. TVS tests, physical printing, actual uninstall/reinstall recovery, radios-off restart and full final device checklist remain unverified. Existing ledger does not support fractional kg quantities; do not change stored quantity/calculation contracts during polish.

Branding note remains report-only: logo says “Arafa”, app title says “Arafah”. Do not edit the logo.

## Resumed verification checkpoint

The user requested continuation. The old wireless endpoint refuses connections; `adb devices -l` and mDNS discovery show no device. The Wi-Fi SSID/BSSID supplied by the owner are not an ADB endpoint; the current Wireless debugging “IP address & Port” has been requested. No live package, ledger or device settings have been changed during this resumed session.

Production debug 1.0.18 (19), package `in.vgl.restaurant`, matches the previous installed signing certificate. Its SHA-256 is `853183b29b77019996669f6c587cdcb374b3c2d4e3df56dcac425d20e1c285f2`. All 67 web files plus generated Cordova bridge files match the current build. The separate sandbox APK has the same web files and its own package ID; it cannot be installed over the live package. Unsigned production release SHA-256 is `558836bcd23530b5f749ad704d4595b5bde5fb418c58aa360402111ae8d9a3fe`, retained as `artifacts/restaurant-pos-1.0.18-release-unsigned.apk`. Full metadata is in `test-results/padgo-resume-artifact-verification.json`.

Prepared private helper scripts accept an explicitly supplied `POS_TEST_SERIAL`. The snapshot/install helper first verifies the Pad Go model and production data path, archives a stopped ledger, preserves all recovered original sale/payment rows while allowing newer owner bills, and rejects source/installed signer mismatches or any intervening data changes. Installation is a separate explicit mode and has NOT run. The sandbox helper tests only `in.vgl.restaurant.polishcheck`, restores rotation in `finally`, verifies the live database checksum stays unchanged, and never commits a paid bill to the owner app. Helpers were syntax-checked; their device execution remains pending reconnection. Existing private recovery scripts must not be rerun against the live ledger.

## Completed resumed-device checkpoint

Fresh private safety evidence is under `test-results/padgo-resume-1793713622625/`. Before update, all 43 protected files and every owner table matched the recovered archive exactly. Production APK SHA-256/signature/package/assets were verified before installation. In-place installation preserved every protected byte; after three cold-process relaunches every owner table and all original images still matched. SQLite integrity and foreign-key checks passed. No owner data restore was performed during this resumed session.

The owner then signed in privately. Seven checks passed on the actual live package: all local tile images decode; latest receipt preview agrees with the ninth saved bill (934.50); the unpaid 405.00 cart has CGST 10.12 / SGST 10.13 / total 425.25; a 20.00 discount gives 404.25; hold/recall retains the unpaid cart; GPay preview cancels without payment; Tamil/dark mode preserves totals and cancelled clear preserves all four items. The cart was then cleared and the owner's English/light display choices restored. Every original row was independently reconciled unchanged afterward. The app normally persists a new empty `cart` draft after these checks: the first test assertion expected all tables byte-for-byte unchanged and was too broad. Its failure was investigated; only that empty draft was added. No account, sale, payment, sequence, adjustment, customer, product, setting or print-attempt row changed. The normal empty draft was retained instead of editing the database to hide the difference.

The separate test app also passed six resumed checks covering native restart durability, wrong password, password toggle/selection preservation, Enter submission, GST/discount, hold/recall and landscape checkout/clear. It is stopped. Automated rotation was denied by Android's shell WRITE_SETTINGS restriction; accelerometer=1 and user_rotation=0 were rechecked unchanged. Physical portrait testing remains pending; portrait and small-phone browser layouts passed. No device permission restrictions were bypassed.

### Actual build and check results

| Check | Corrected-build result |
| --- | --- |
| Restaurant Node suite | 89 passed before pause; no further runtime edits afterward. |
| Full browser suite | **60 passed**, 5.0 minutes; includes backup-inspection isolation and all billing regression cases. |
| JavaScript lint | Passed with zero warnings on resumed run. |
| Vite build | Passed before pause; all 67 resulting web files matched debug, unsigned release and sandbox APKs on resume. |
| Android debug / lint / unit-test invocation | Build successful; unchanged Java test results cached. |
| Android release assembly / vital lint | Build successful; unsigned release retained, not installed. |
| Native sandbox backup inspection/rejection/restore | Seven recorded pre-pause checks passed, with all 23 backup images and unchanged owner database hash. |
| Production install / startup | All 43 protected files unchanged through install; every owner table and original image preserved through startup. |
| Production signed-in checks | Seven passed; nine bills retained, no test payment, empty cart afterward. |
| Type check | No separate type-check task is configured; no TypeScript-check pass claimed. |

### Startup measurements

The Pad Go debug samples use the same opt-in stage marks. The first attempt did not retain the diagnostic localStorage flag across immediate process termination; it was discarded, then the flag was allowed to flush before sampling. The flag was restored to absent and verified absent afterward. Three valid cold-process relaunch samples: navigation-relative login paint **567.6 / 508.5 / 535.3 ms**, interactive **1402.0 / 1251.4 / 1280.0 ms**. Android Activity TotalTime was **2317 / 2131 / 2239 ms**. Activity startup and WebView navigation have different origins: do not add them or call the navigation paint value a launcher-to-login time. These results do not establish the TVS target.

| Device / variant | Scenario | Before | After |
| --- | --- | --- | --- |
| TVS / debug | First install | Not measured | Not measured: TVS unavailable. |
| TVS / debug | Relaunch | Not measured | Not measured: TVS unavailable. |
| TVS / release | First install | Not measured | Not measured: TVS unavailable; release unsigned. |
| TVS / release | Relaunch | Not measured | Not measured: TVS unavailable; release unsigned. |
| Pad Go / debug | Fresh install | Not measured | Not measured for production: owner data deliberately preserved. |
| Pad Go / debug | Existing-ledger relaunch | No comparable marked baseline | Median navigation paint 535.3 ms, interactive 1280.0 ms; three samples, limitations above. |
| Pad Go / release | Fresh install / relaunch | Not measured | Not measured; no release runtime installation. |
| Desktop production web | Fresh storage | Paint 740.0 / interactive 720.5 ms | Paint 175.1 / interactive 350.4 ms; earlier phase measurements, not device acceptance. |
| Desktop production web | Locked-owner relaunch | Paint 196.4 / interactive 169.0 ms | Paint 62.6 / interactive 108.2 ms; earlier phase measurements, not device acceptance. |

### Billing regression: unchanged before and after

These numbers agree across the automated on-screen cart, saved sale/payment, print document, reprint, Sales/Reports and complete backup restore. Browser print submission was stubbed; physical paper output was not tested. Native live checks were unpaid; native paid/restore checks used the separate synthetic package only.

| Case | Gross | Discount | Taxable | CGST | SGST | Round off | Total before = after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| EGG PORIAL + BOILED EGG + KUDAL GRAVY + EMPTY BIRYANI | 405.00 | 0.00 | 405.00 | 10.12 | 10.13 | 0.00 | 425.25 |
| Same cart, bill discount | 405.00 | 20.00 | 385.00 | 9.61 | 9.64 | 0.00 | 404.25 |
| Existing fixed half-kg portion | 160.00 | 0.00 | 160.00 | 4.00 | 4.00 | 0.00 | 168.00 |
| Same 405 cart, rounding ON | 405.00 | 0.00 | 405.00 | 10.12 | 10.13 | -0.25 | 425.00 |

A continuously weighed 0.500-kg transaction could not be tested: the unchanged ledger stores integer portion counts, with separately priced kg/half-kg products. Adding fractional-weight selling would change the existing business/schema contract and was not undertaken.

### Final requirement checklist

“Verified” means the stated automated/source evidence, supplemented by the Pad Go checks above; it does not imply TVS or physical-print acceptance.

| Item | Status | Evidence / limitation |
| --- | --- | --- |
| A1 | Implemented but not verified | Seven-stage/paint/interactive marks; desktop before/after and Pad Go debug relaunch measured. Full native fresh/debug/release baseline absent. |
| A2 | Verified | Early shell/readiness/queued submit browser tests; actual native login and readiness passed. Native early-submit fault injection not performed. |
| A3 | Verified | Deferred optional work and stalled image/backup browser tests; native guards/background initialization completed. |
| A4 | Verified | Cached original branding; edit/removal/restart browser tests and actual branded native shell. |
| A5 | Verified | Current-version no-write initialization, fresh seed and legacy migration tests. |
| A6 | Not done | Heavy features lazy-loaded; strict preview-only WASM exception remains for safe isolated native backup validation. Unsafe native validation removed. |
| A7 | Implemented but not verified | Blue native background/config compiles; shell observed. No recorded first-frame/no-white-flash proof. |
| A8 | Verified | Failure/retry browser fault injection passed. Physical native open-failure injection not attempted. |
| A9 | Not done | Actual TVS and signed release measurements unavailable; no target achievement claimed. |
| A10 | Not done | Optional ABI filtering omitted to avoid unsupported hardware assumptions. |
| B1 | Verified | Real button, 44px target, bilingual labels; native selection/value preserved. |
| B2 | Verified | Recovery label/link aligned with fields across tested browser sizes and observed native shell. |
| B3 | Verified | Helper sizes and contrast tests in both themes; native shell visually inspected. |
| B4 | Verified | New offline wording translated; recovery workflow browser-tested. |
| B5 | Verified | No username prefill/new storage; autocomplete retained. |
| B6 | Verified | Cached original logo, white padded badge; image unchanged. |
| B7 | Verified | Panel balance/headline/subtext retained; native shell inspected. |
| B8 | Verified | Inline error, loading/readiness, Enter/focus browser tests; native wrong password/Enter in sandbox and private owner login passed. |
| C1 | Not done | Whole portion counts verified. True fractional weight display/test unsupported by existing integer-portion ledger; no calculation/schema change made. |
| C2 | Verified | Existing default-OFF setting exposed; ON/OFF saved/receipt/report/restore reconciliation passed in disposable tests. |
| C3 | Verified | Single-column totals order and alignment verified; arithmetic unchanged. |
| C4 | Verified | Collapsed breakdown and pinned checkout passed six browser sizes plus actual 1070×716 native landscape. Physical portrait/TVS pending. |
| C5 | Verified | Existing settings-derived menu price/GST label retained and native inspected; no new hardcoded rate. |
| C6 | Verified | Singleton Standard hidden; multi-portion restoration test passed. |
| C7 | Verified | Full sidebar name remains readable in two native landscape lines. Compact sidebar behavior unchanged. |
| C8 | Verified | Native cancel retains cart; confirmed clear and hold/recall passed. |
| C9 | Verified | Read-only configured receipt label is explicit; invoice logic unchanged. |

### Files changed, grouped by phase

Phase A (`b0caee2`): `restaurant/index.html` renders the shell early; `restaurant/entry.js` handles readiness, failure/retry and paint-triggered splash hide; `restaurant/app.js` splits core/access from optional startup; `restaurant/access-ui.js` exposes readiness/loading; `restaurant/preferences.js` translates startup states; `restaurant/public/login-branding.js` applies the optional pre-paint cache; `restaurant/public/startup-profile.js` contains opt-in marks; `restaurant/repository.js` avoids repeated current-version initialization; `restaurant/drivers.js` keeps preview loading lazy (the introduced native validator is withdrawn and corrected below); `restaurant/original-billing-template.js` provides early cached identity integration; `capacitor.config.json` and `android/app/src/main/res/values/styles.xml` set splash/window blue; `package.json`/`package-lock.json` and `android/app/capacitor.build.gradle`/`android/capacitor.settings.gradle` add/sync the splash plugin; `scripts/profile-restaurant-startup.mjs` measures stage marks; `tests/restaurant/startup.test.js`, `tests/restaurant/native-validation.test.js`, `tests/restaurant-browser/startup.spec.js` cover startup paths; the startup report records the checkpoint.

Phase B (`2cac5dc`): `restaurant/access-ui.js` adds the password toggle and login interaction presentation; `restaurant/index.html` adds its real button and updated helper markup; `restaurant/preferences.js` adds English/Tamil labels; `restaurant/workspace-style.css` adjusts badge, balance, helper contrast, recovery alignment and focus; `tests/restaurant-browser/login-polish.spec.js` verifies toggle/geometry/contrast; `tests/restaurant-browser/workspace-upgrade.spec.js` updates the changed helper assertion; the startup report records the checkpoint.

Phase C (`ea3d42d`): `src/vglpos/web/static/src/js/pos.js` formats portion counts/labels, prompts clear and displays configured receipt status; `src/vglpos/web/templates/pos.html` orders/collapses totals and adds the clear dialog; `restaurant/style.css` preserves checkout visibility and brand wrapping; `restaurant/app.js` retains portion metadata for display; `restaurant/preferences.js` translates the display additions. `restaurant/access-ui.js`, `restaurant/entry.js`, `restaurant/public/startup-profile.js` finalize the early toggle/diagnostic compatibility. `tests/restaurant-browser/billing-polish.spec.js`, `billing-polish-regression.spec.js` and `recovery-polish.spec.js` cover changed behavior; `access-helper.js`, `converted-billing.spec.js`, `receipt-performance.spec.js`, `restaurant.spec.js`, `startup.spec.js`, `vgl-brand.spec.js` update affected fixtures/assertions. The startup report records the checkpoint and measurements.

Corrective checkpoint after device failure: `restaurant/app.js` restores the isolated in-memory factories; `restaurant/drivers.js` refuses native validation before any connection; `tests/restaurant/native-validation.test.js` tests fail-closed behavior; `tests/restaurant-browser/backup-inspection-isolation.spec.js` guards inspection/cancel against replacing another ledger; `android/app/build.gradle` identifies production 1.0.18 (19). This device report and the warning in `docs/restaurant/startup-polish-2026-11-03.md` supersede the withdrawn artifact's claims. Local `START_HERE.md`/`HANDOFF.md` are updated; private scripts/results remain ignored and must not be published. No unrelated existing source edits are included in this corrective commit.

### Remaining limits / intentionally unchanged

No real TVS access, signed-release runtime, physical printer/reconnect, actual production uninstall/reinstall with SAF reacquisition, radios-off native cold start, native DB-open failure injection or physical portrait acceptance. Browser recovery/fault/portrait tests and isolated native restore do not substitute for those. Existing tax/receipt/authentication calculations, schema, synchronous=FULL, owner credentials, historical sales, image assets and append-only shared backup behavior were preserved. No KOT, tables, order types or new billing feature was added. Existing unrelated dependency findings and unrelated dirty workspace files were not changed.

Branding observation only: the image says **Arafa**, while the app says **Arafah**. The logo was not edited.
