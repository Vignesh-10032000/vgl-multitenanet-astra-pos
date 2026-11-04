# Original billing quality gate — 29 October 2026

This report concerns the converted original billing controller/template. It is **not production or device acceptance**. Source ownership and the remaining management-screen work are recorded in `original-billing-conversion.md`.

## Implemented and verified locally

| Check | Fresh result in this session | Scope |
| --- | --- | --- |
| `node --test tests/frontend/*.test.js tests/restaurant/*.test.js` | **40 passed**, 0 failures | Original money/payment helpers and 200 tax parity fixtures; restaurant GST, snapshots, atomic failure rollback, retries, final numbering, corrections, >500 bills, real SQLite reopen, backup/restore, CSV/XLSX and new billing adapters/holds |
| `npm run test:restaurant:browser` | **13 passed**, 0 failures | Original cart/quantity/discount/undo, Cash/GPay, no-network checkout, saved receipt/reprint, local photos/customers/drafts, holds/quick keys, duplicate taps, simulated print failure, original baseline panel geometry, phone layout, exports and disposable browser restore |
| `npm run lint:js` | **0 errors, 0 warnings** | ESLint recommended checks plus undefined/unused names and forbidden dynamic execution; restaurant JS, converted/shared frontend helpers, tests and profiling/environment scripts |
| `npm run scan:restaurant` | **0 findings**, 23 files, 4 local rules | Semgrep checks dynamic execution, forbidden server billing calls, premature provider success and embedded access-key patterns. This is a limited local ruleset, not a comprehensive security certification. Metrics/version checks are disabled. |
| Android build helper `-Lint -UnitTests` | Build passed; **4 Java tests passed**; Lint **0 errors, 19 warnings** | Debug APK compile and pure-Java document writer tests for success/flush/close, failed write, failed close and missing provider stream. These are not an Android document-provider test. |
| Independent exact arithmetic | SymPy rational check passed | ₹170 included GST: taxable 16,190 paise + CGST 405 + SGST 405 = 17,000; no floating-point persisted money |
| Browser JavaScript diagnostics | No page errors in regression/performance runs | Local desktop Chromium through Playwright and Chrome DevTools Protocol |

The original `npm test` command also passed 36 tests earlier in this session before the four new adapter/hold tests were added. The 40-test command above was run after those additions. Do not conflate the old 500-bill outbox test with the standalone restaurant ledger: it remains a legacy helper fixture and the converted runtime does not import that outbox.

Android Lint warnings concern existing tool/dependency/resource/platform configuration (including newer Android orientation behavior); no error suppression or lowered test threshold was added. The production web build retains the known lazy ExcelJS chunk-size warning. JavaScript remains vanilla ES modules: no TypeScript conversion/type-check coverage is claimed. Native Java compilation checks the native source types.

## Failures reproduced before correction

- **BILL-UNDO-01:** after completing a bill, its still-visible Undo callback restored an item into the new cart. The test first failed with one cart line instead of zero, then passed after scoping callbacks to the billing operation.
- **BILL-UNDO-02:** remove, reselect the same portion, Undo created two lines with the same product ID. The test first failed with two lines instead of one; undo now merges the quantity through the existing exact quantity path and checkout succeeds.
- **HOLD-01:** repository recall could replace another durable active cart despite the UI guard. The test first failed with a missing rejection. The repository now rejects the overwrite inside the transaction; both active cart and hold remain.
- **BILL-PHOTO-01:** the original stylesheet loaded after restaurant overrides, reducing the photo area to 44 px. Import order now preserves the 96 px photo area/210 px tap tile. The final browser suite verifies the actual dimensions.
- **Android export close:** source tracing found `resolve(saved)` inside the open-stream try block, before automatic close. `DocumentWriter` now returns only after close, so a failed close reaches the rejection path. The four Java tests cover the writer; actual provider/picker lifecycle remains unverified.

## Desktop performance baseline

`npm run profile:restaurant` records a local Chrome DevTools trace and machine-readable measurements under `test-results/restaurant-performance/`. It creates a disposable browser context and a synthetic in-memory ledger; it does not restore or write live app data. It measures navigation/ready time, pointer-to-cart-paint, forced-GC heap/DOM/listener counters after warm-up and 10/20 repeated billing/navigation cycles, and a restored 1,000-bill report/CSV download. Report/download wall times include browser automation overhead. Tracing itself also has overhead.

One baseline recorded at `2026-10-29T15:35:42Z`, desktop Chromium **149.0.7827.55**:

| Measurement | Observed |
| --- | --- |
| Ready after initial navigation | 421.5 ms |
| Pointer-to-cart-paint, 23 samples | median 22.4 ms; p95 35.7 ms; max 36.9 ms |
| DOM nodes / JS listeners | 2,487 / 140 at baseline, after 10 and after 20 cycles |
| Forced-GC JS heap used | 3,027,952 → 3,186,780 → 3,179,096 bytes |
| 1,000-bill table render | 1,101.8 ms including automation overhead |
| 1,000-bill CSV download | 1,468.1 ms including automation overhead |
| Page errors | 0 |

These figures are diagnostic desktop measurements, not TVS startup/touch/PSS or all-day memory acceptance. Stable DOM/listener counts do not prove absence of leaks. See the saved JSON/trace for exact provenance and subsequent reruns.

## Requested skills and tools evaluated

- Applied installed `engineering-quality-gate`, Capacitor development/plugin, `android-cli` and `testing-setup` instructions. Preserved the Capacitor WebView/vanilla JS stack, existing JUnit4 and browser/SQLite tests. Project instructions supersede generic DI/Compose/iOS/cloud defaults; none were introduced.
- Used Serena overview/body/reference navigation to trace completion, UI bindings and repository boundaries. Used Context7 for the Vite HTML transform/ESLint configuration, Capacitor v8 MCP for web/native sync and Android documentation for Storage Access Framework/printing lifecycle.
- Evaluated [Obra systematic-debugging](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md) and [verification-before-completion](https://github.com/obra/superpowers/blob/main/skills/verification-before-completion/SKILL.md). Used their root-cause and fresh-evidence approach for the named red/green cases. Public instructions were read into the ignored local tools folder; no entire skill collection was installed.
- Evaluated [Google android-profiler](https://github.com/android/skills/blob/main/profilers/android-profiler/SKILL.md), its setup and recording orchestrator. Useful for the next actual device system/startup trace, with heap profiling as a separate workflow. Google Android CLI **1.1.16717390** initialized and `info`, profiler help and emulator listing ran with metrics disabled. No connected device/emulator was available for a capture.
- Evaluated [Chrome DevTools memory-leak-debugging](https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/skills/memory-leak-debugging/SKILL.md). The current MCP exposes snapshot capture but not advanced heap comparison/retainer tools; `--memoryDebugging` is absent in its configuration. MCP navigation to local Windows Vite timed out. Used local CDP trace/forced-GC counters through Playwright instead; no raw heap snapshots were parsed, no intentional detached-node cache was nulled, and no global MCP configuration was changed.
- The Windows Java/Android CLI and Semgrep initially failed at loopback/socket setup with the default temporary path. The project-local short `.tools/tmp` path resolved both; the reproducible build/security commands include it.

## Not verified on a device

APK installation, native SQLite force-stop/reboot recovery, native backup/restore, Android provider/picker cancellation/write/close/lifecycle behavior, actual TVS startup/touch/frame/memory performance, and physical custom-APK printing/reconnect/paper-out remain **NOT VERIFIED**. ADB returned no attached devices and the CLI emulator list was empty. The already-proven USB connection and print service remain the chosen route; no direct USB integration was justified or added. Follow `device-acceptance.md` before live use.

No push, publication, message to another person or private-reference upload was performed. Existing local work and the original prior APK are retained.

## Storage relocation requested by the owner

The POS remains at `D:\vgl-restaurant-pos`. The owner's scope is POS tools and caches only. The Android SDK, Android user/CLI data and Playwright browser binaries are copied to `.tools/` on D:, checked file-by-file with SHA-256, then the old C: directories are replaced with compatibility junctions. No application source outside this checkout is changed. `scripts/project-environment.mjs` preloads D: paths for project command temporary files, browser profiles, SDK/user data, Gradle, npm and future UV caches. `.npmrc` also directs direct project npm commands to D:. Shared installed Windows/Codex/Node/Python applications are outside this relocation.

The exact moved paths, byte counts and C:/D: free-space measurements are recorded in `storage-migration.json`. Post-migration browser/ledger and Android checks verify the relocated tool paths. Prior local work, references and APKs remain preserved.

Post-move verification: all **29 restaurant Node tests** and **13 browser scenarios** passed with the D: environment. Android `-SkipWebBuild -Lint -UnitTests` completed successfully from the relocated SDK (1m 54s). Android CLI `info` and ADB `version` resolve to D:. All three old cache locations were verified as junctions to D:. Approximately **2.33 GB** of file content was moved; C: showed approximately **3.26 GB free** afterward. The original 1.0.1 APK SHA-256 remains unchanged, and the 1.0.2 artifact still matches the final built APK.
