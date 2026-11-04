# Restaurant POS reliability audit — 31 October 2026

One checkout validation defect was reproduced and corrected. Final results: **75 Node checks, 27 browser scenarios and 11 freshly executed Java tests passed**. Isolated 100/500/1,000-bill desktop workloads and a 50-bill native SQLite workload reconciled without duplicates or partial bills. This is scoped verification, not production or TVS acceptance.

## Finding and change

**AUDIT-01 — invalid discount silently accepted: corrected and regression verified.** `Ledger.checkout()` used `discount_paise || 0`, allowing `NaN`, `false` and an empty string to become zero and create a completed bill. The new test failed before the change with `Missing expected rejection`; changing both request normalization and calculation to `?? 0` preserves omitted defaults while allowing the existing integer validator to reject invalid values. No tax formula, menu price, numbering, layout, historical bill or payment behavior changed.

Pre-fix evidence: `new-tests-before-fix.log` (9 passed / 1 failed). Post-fix evidence: `new-tests-after-fix.log` and final full suite. Named regression: `tests/restaurant/reliability.test.js`, `AUDIT-01`.

## Category results

PASS applies to the stated scope, not to every hardware-dependent case. Evidence filenames in this report are relative to **`D:\vgl-restaurant-pos\test-results\reliability-audit\`** unless another directory is specified.

| Category | Status | Passed / failed | Evidence | Remaining risk |
| --- | --- | --- | --- | --- |
| JavaScript unit tests | PASS | 75 / 0: 64 restaurant + 11 preserved frontend checks | `final-node.log` | Not exhaustive state/input coverage |
| Property-based tests | PASS | 6,000 generated financial cases + 60 SQLite histories; seed 20261031 | Financial/reliability suites, `coverage.log` | Bounded generators |
| Mutation checks | PASS | 6/6 deliberate financial mutations detected; unmutated control passes | `mutations/results.json` and per-variant logs | Focused semantic audit, not an exhaustive StrykerJS score |
| Internal API contracts | PASS | Invalid checkout inputs, retry, commit ambiguity, access lockout, provider failures and actual native bridge calls | Node/browser/device evidence | Not every Android lifecycle/plugin error injected |
| SQLite transactions | PASS | Eight checkout write/pre-commit failpoints, constraints, interleaved reads, reopening and native second-tender rollback | `reliability-final.log`, `device/results.json` | Native process/power interruption during writes unverified |
| Inclusive GST | PASS | Independent BigInt properties, preserved fixtures, SymPy rational checks; ₹105→₹100 + ₹2.50 + ₹2.50; ₹170 stays ₹170 | `symbolic-money.json`, GST suite, receipt screenshot | Existing line rounding retained: odd tax paise go to SGST; bill round-off remains separate |
| Payment calculations | PASS | Cash/UPI/split, shares, change, invalid tenders, rollback, retry, filtered reports | Node/browser suites and 50 native split bills | Cashier-recorded UPI is not gateway-confirmed settlement |
| Held bills/drafts | PASS | File reopen/recall plus 300 hold/draft cycles across stress workloads and existing browser recovery | `reliability-final.log`, `stress/results.json` | No forced process death on owner's running app |
| Stress/soak | PASS | 100 + 500 + 1,000 desktop bills; 1,000 products, 22 images, 100 hold cycles per volume; 20 browser cycles | `stress/results.json`, `desktop-metrics.json` | Bounded runs, not a whole shift or TVS endurance acceptance |
| Browser E2E | PASS | 27 / 0, 2.7 minutes; baseline 26 / 0, 1.9 minutes | `baseline-browser.log`, `final-browser.log` | Desktop Chromium/sql.js differs from Android SQLite/WebView |
| Android native tests | PASS | Fresh 11 / 0 JUnit; separate actual bridge checks: 50 bills, eight retry calls, injected rollback, reopen and restore | `android-unit-fresh.log`, Java XML, `device/results.json` | One JUnit check is scaffold arithmetic; ten cover document helpers. Bridge audit injects local Ledger definitions into installed 1.0.9, not a newly installed APK |
| Reports/exports | PASS | Known-data filters; XLSX parsed through 1,000 bills; CSV formula/Unicode checks; all 41 PDF pages parsed/rendered | Stress files, browser/Node logs, `pdf/results.json` | Raster PDFs have no selectable text; 1,000-bill PDF memory/time not measured. Records may continue on the next page |
| Backup/restore | PASS | Exact image/snapshot round trips, v1 compatibility, staging/restore failures, permission loss, changed document, provider mismatch | Backup/photo/migration suites, stress/native results | Native bridge backup used synthetic in-memory images. Actual Android image persistence has earlier documented evidence; reinstall/SAF recovery was not retested |
| Printing | BLOCKED | Saved-receipt HTML/GST/reprint/preview pass; zero physical print attempts | GST suite; `test-results/restaurant-artifacts/gst-receipt.png` | No printer/TVS available: paper, font, reconnect, paper-out and reboot tests remain |
| Security/static analysis | FAIL | ESLint passes; Semgrep 4 rules / 44 production files / 0 findings; npm audit reports 13 moderate affected dependency nodes, 0 high/critical | `final-lint.log`, `semgrep.log`, `dependency-audit.json` | Dependency findings remain open; scoped scan is not full security assurance |
| Android build | PASS | AssembleDebug, Lint 0 errors / 19 warnings, signature verification, 45 matching web assets | `android-build.log`, `apk-signature.log`, `apk-verification.json` | Debug-signed candidate not installed; existing Lint warnings remain |
| HTTP load testing | NOT APPLICABLE | No restaurant server required or added | `TEST_PLAN.md` | Legacy Flask tests target the older server app |
| Type checking | NOT APPLICABLE | Vanilla JavaScript; no separate type-check command configured | Package scripts | Executed tests/lint are not a static type proof |

## Measured desktop workloads

Windows / Node v24.12.0, disposable file-backed SQLite, `synchronous=FULL`. Async calls are batched eight at a time and serialized by Ledger. Other verification tools ran concurrently; these diagnostic measurements are not TVS budgets.

| Bills | Billing elapsed | Report | XLSX generation | Image backup | Validated restore | SQLite bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 1,593 ms | 9.8 ms | 220 ms | 45 ms | 228 ms | 524,288 |
| 500 | 6,688 ms | 33.2 ms | 358 ms | 58 ms | 279 ms | 1,302,528 |
| 1,000 | 13,117 ms | 102.0 ms | 762 ms | 109 ms | 798 ms | 2,265,088 |

Write success was 100%; three deliberate interrupted writes are counted separately. Each workload reopens the file, checks SQLite integrity/FKs, compares restored snapshots and all 22 JPEG strings, parses XLSX invoice amounts to integer paise, and reconciles Cash + UPI = net. There were 160 retry requests and 300 hold/recall cycles. The largest complete backup was 3,776,014 bytes. Query/filter timings measure the real catalog service plus a synthetic in-process text filter, not UI search rendering.

Desktop Chromium profiling: ready at 479.8 ms; 23 tap-to-cart paint samples, median 28.7 ms / p95 29.7 ms; 1,000-bill Sales render 508 ms including automation overhead. After explicit GC, JS heap was 3,278,216 B initially, 3,370,656 B after ten cycles and 3,399,924 B after twenty; document/node/listener counts stayed 2 / 3,176 / 157. No page exceptions were recorded. This short observation cannot prove leak absence. Node memory samples include GC/export/fixture retention and are not Android baselines.

## Native evidence and preservation

Connected **OPD2305 / Android 14**, WebView Chrome 155.0.8059.43; installed app remains **1.0.9 (10)**. No installation, launch/restart, login change, live sale/restore, shared-backup write or print was performed.

The script loaded current local Ledger/backup definitions through the existing development WebView and called the actual Capacitor SQLite bridge against new UUID-named `audit_*` databases. Fifty split bills reconciled to **848,775 paise**, with final-number uniqueness, second-tender rollback, exact close/reopen recovery, integrity/FK checks and synthetic backup restoration. Sequential checkout median **150.3 ms**, p95 **157.4 ms**; total audit **14.84 s**. A single post-run memory sample was 204,012 KiB total app PSS, neither a peak nor endurance measurement.

Read-only before/after hashes matched for all owner tables: six sales, 13 lines, seven payments, three corrections, four correction payments, credentials/preferences and 36 product/photo references. Metadata hashes matched for all **nine shared backups**. The **₹340 unpaid draft and open demo QR** were unchanged. Three explicit synthetic database files were closed and retained for inspection; their names are in `device/results.json`. They are not restaurant ledgers.

The initial native harness attempted an unsupported data-URL import and failed before database work. The corrected local-bundle harness passed; the tooling attempt remains in `device-import-attempt.log`. Android CLI docs indexing also failed with a loopback connection error; ADB/build/tests and the Capacitor documentation MCP remained available.

## Open findings and acceptance limits

The npm audit reports two underlying advisory families: `glob` AbortSignal traversal bypass (`>=9.0.0 <=14.0.1`) and `minimatch` globparts amplification (`<11.0.1`), affecting 13 dependency nodes including tooling and ExcelJS's Node archive chain. npm suggests several older major versions as fixes. No forced downgrade or untested transitive override was applied; offline browser-bundle exploitability was not established. Compatible upstream fixes still need review.

Before release acceptance: newly built candidate installation on an isolated device; actual TVS cold/warm startup, search/tap/save latency, CPU/memory and sustained shift use; forced interruption; picker lifecycle; real reinstall/SAF reconnection; native image restoration; and physical 80 mm printing with USB/paper/printer recovery. No TVS numerical budget or production-readiness claim is invented.

## Artifacts and commands

Candidate **`D:\vgl-restaurant-pos\artifacts\restaurant-pos-1.0.9-audit-debug.apk`**, 15,445,567 bytes, SHA-256 **`69311b9bedc804f61f3df425b7c150c1e5a72a8c431f2ecd32be1750c5c43444`**. It keeps version 1.0.9 (10) under a distinct filename; the earlier APK is preserved. V2 signature verifies with the existing Android Debug signer. All 45 Vite files match; only Capacitor-generated `cordova.js` and `cordova_plugins.js` are extra. **This candidate was not installed.**

Run from `D:\vgl-restaurant-pos` in PowerShell:

```powershell
New-Item -ItemType Directory -Force test-results/reliability-audit | Out-Null
npm.cmd test
npm.cmd run test:restaurant:coverage
npm.cmd run test:restaurant:properties
npm.cmd run test:restaurant:mutations
npm.cmd run test:restaurant:stress -- --bills=100,500,1000 --cycles=100 --products=1000
npm.cmd run build:restaurant
npm.cmd run test:restaurant:browser
npm.cmd run profile:restaurant
npm.cmd run lint:js
npm.cmd run scan:restaurant
npm.cmd audit --json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-restaurant-android.ps1 -SkipWebBuild -Lint -UnitTests
```

Full Node suite: 9.50 s; coverage: 13.83 s; Android build/lint: 1 min 19 s. The build initially reused Java test results; a fresh task rerun subsequently executed all eleven tests in a 33 s Gradle run:

```powershell
$env:JAVA_HOME = 'D:\vgl-restaurant-pos\.tools\jdk\jdk-21.0.12.1+1'
$env:ANDROID_HOME = 'D:\vgl-restaurant-pos\.tools\android-sdk'
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$env:GRADLE_USER_HOME = 'D:\vgl-restaurant-pos\.tools\gradle'
$env:PATH = (Join-Path $env:JAVA_HOME 'bin') + ';' + $env:PATH
Push-Location D:\vgl-restaurant-pos\android
try { .\gradlew.bat :app:testDebugUnitTest --rerun --no-daemon } finally { Pop-Location }
```

Actual native bridge command (explicit connected serial, already-running debug WebView; writes only UUID audit databases):

```powershell
node --import ./scripts/project-environment.mjs scripts/audit-restaurant-device.mjs --device=XCQWFQKR8945WKLN
```

Fresh Java XML: `android/app/build/test-results/testDebugUnitTest/`. Browser screenshots/PDFs: `test-results/restaurant-artifacts/`. Poppler was unavailable; the read-only PDF render used project-local pypdf 6.21.4 / pypdfium2 5.14.0 via `.tools/audit-pdfs.py`. All 9 + 32 pages rendered; contact sheets, selected full pages, receipt and billing screenshots were visually reviewed. PDFs have zero extractable text. SymPy 1.14.0 rational checks and ZIP comparison are retained in `.tools/record-reliability.py`. These are QA tools, not app dependencies.

Coverage: `coverage.lcov`, **87.36% lines / 85.97% branches / 89.72% functions** across loaded restaurant modules. `domain.js`: 100% lines / 91.67% branches; `repository.js`: 98.08% lines / 90.74% branches; `backup-service.js`: 100% lines / 100% branches. Node's report omits UI/browser/native modules it never loads; these figures are not whole-app coverage. No threshold was lowered.

Retained deliverables: `TEST_PLAN.md`, this report, financial property/reliability Node suites, storage-failure browser scenario, stress/mutation/native audit scripts, and raw evidence. `fast-check 4.10.2` is a development dependency; Node/Playwright/JUnit remain in use. Production source changes are limited to two discount-default expressions. All pre-existing local work, bills, images, installation markers and shared backups remain. No push, publication, messaging or private-reference upload occurred.
