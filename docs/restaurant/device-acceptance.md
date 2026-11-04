# Device acceptance still required

Update, 30 October 2026: OnePlus and Samsung physical-device smoke checks are recorded in `oneplus-device-2026-10-30.md` and `samsung-device-2026-10-30.md`. They cover the explicitly listed cases only. The TVS performance and physical-printing sections below remain required; the original 29 October environment observation is historical.

No Android device was attached on 29 October 2026; ADB listed no devices and Android CLI listed no installed emulators. None of the following cases has passed on Android in this session. Use a disposable test installation/data set before any restore, destructive data test or synthetic high-volume billing. Preserve a complete validated backup of any existing live installation. Never clear live app data for a test.

## Record the environment

Record device model, Android/API, app version/hash, System WebView version, screen size/density, storage free space, selected print service and printer/connection. Do not infer ABI from the terminal model and do not root the device. Use the project-local Android CLI with metrics disabled. On this Windows host, set `TEMP`, `TMP` and `-Djdk.net.unixdomain.tmpdir` to the project's `.tools/tmp` before CLI/profiler commands; the default long path produced a loopback error.

```powershell
& "$env:LOCALAPPDATA/Android/Sdk/platform-tools/adb.exe" devices -l
& '.tools/android-cli/android.exe' --no-metrics info
& '.tools/android-cli/android.exe' --no-metrics profiler systemtrace --help
```

Use the chosen device serial explicitly when multiple devices are present. Install the versioned test APK; do not uninstall an existing live copy or reset its database. Inspect the installed package/version before any lifecycle test.

## Native SQLite and restart

1. In airplane mode, bill one ₹170 portion with ₹200 cash. Record final number, GST breakdown, payment and change. Create a GPay bill; record the cashier acknowledgement and underlying `upi` report filter.
2. Force-stop **the selected test installation**, reopen offline and verify both saved bills, exact totals, menu images/customer and final numbers. Reprint each without changing bill count or revenue.
3. Repeat after a full device reboot in airplane mode. Check that the next bill uses the next final number and old receipts still show saved product/store/tax snapshots.
4. Keep an unsaved cart with quantities/customer/discount; force-stop after the saved-cart indicator, reopen and review it. Test rapidly repeated completion taps and interrupt around commit. Reconcile sale, lines, payment, sequence and draft state. A partial bill is a failure; one committed bill plus a safe reprint is acceptable.
5. In disposable data, test storage full/write failure and retry. Never generate physical receipts for the existing 500+ capacity test. Exercise date/FY boundaries through controlled fixtures, not by changing the live counter's clock.

## Backup, restore and Android files

1. Back up a test ledger containing local dish/logo images, both payment types, discount/rounding, a correction, drafts/holds and preferences. Save through a local Storage Access Framework provider and reopen the saved file independently.
2. Restore it into a separate disposable installation. Check image checksums, complete settings, saved snapshots, all registers/corrections/print audit and next numbering. Do not restore an older numbering counter into live use.
3. Reject truncated/modified/missing-image/inconsistent-payment backups while retaining current active data.
4. Export CSV/XLSX/PDF offline to a local provider. Verify saved bytes, parse register/payment/line totals, inspect Tamil PDF pages and monthly boundaries. Test picker cancellation, permission denial, low storage/provider write/close failure and activity interruption. A cancelled/failed save must not show success. The four local Java writer tests are not provider acceptance.

## TVS performance

The owner's governing target is the TVS, not the OnePlus. Read `tvs-performance-baseline.md` for the collected hardware evidence, unknowns and resource constraints. OnePlus functional tests on 30 October 2026 do not fulfill this section. Historical RAM/free-space snapshots are not guaranteed runtime budgets, and storage capacity is not storage speed.

Use Google's `android-profiler` recording workflow for **system trace/startup** first; run heap profiling separately. Record Android CLI/profiler version and trace settings. Use a debug/profileable test build; no root is required. Capture cold and warm startup, 20 repeated billing/cart/payment/reprint/navigation cycles, photo replacement/loading, and a 1,000-bill report/export fixture. Record cold/warm ready time, tap-to-cart paint and quote completion, frame/jank/long-task evidence, Java/native PSS/heap and WebView/JS counters before/after GC/idle. Keep allocation/trace overhead explicit.

Compare repeat runs on the **actual TVS**, with the same build/data, thermal state, background load and screen configuration. Desktop Chromium timing and forced-GC counters are diagnostic baselines only. Inspect the large-report table/export memory peak; stable counters after 20 desktop cycles do not establish absence of native or long-shift leaks.

## Physical printing through the established service

Select ESC POS USB Print Service from Android PrintManager. Use a saved test bill; verify original 80 mm hierarchy, printable width, Tamil/rupee wrapping, independent portions, own identity, split GST, logo and independently checked merchant QR. Record actual paper output and compare against the style reference, not its shop details.

For each case record bill number, print-attempt state, paper result and unchanged ledger totals: normal print; repeated reprint; USB unplug/replug; printer power cycle; paper-out followed by replenishment/reprint; app restart; device reboot. “Submitted” is not settlement or physical-print confirmation. Do not introduce direct USB, root, KOT or drawer functionality unless a demonstrated unmet requirement justifies separate work.
