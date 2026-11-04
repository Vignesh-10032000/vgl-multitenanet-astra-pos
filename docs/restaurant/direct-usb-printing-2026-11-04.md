# Direct USB receipt printing — 4 November 2026

**Superseded routing:** see [the RP 3230 routing correction](printer-routing-2026-11-04.md). Version 1.0.20 separates direct USB from Android's PDF/service panel and adds setup for the PDF-proven optional service. Earlier selector/fallback descriptions below document the original candidate.

Adds an app-local Capacitor `RestaurantPrinter` plugin. Inspection and changes were limited to printing, its saved-sale/print-attempt interfaces, Android configuration, related tests and required project documents. No new dependency, schema, billing/GST calculation, analytics or backup/restore change.

## Operation

Open a saved receipt and tap Print. Choose the connected ESC/POS USB printer and grant Android USB access when prompted. The selector also retains **Use Android print service**, which opens the existing print-service path before any direct USB bytes are sent. Cancel leaves the bill saved. Browsers retain their existing print dialog.

The direct path reuses `receiptHTML`, bundled styles/fonts, immutable identity, item/payment/tax snapshots, logo and merchant QR. A separate local-only WebView renders the existing 80 mm layout into at most 256 bitmap rows at a time; ESC/POS `GS v 0` raster packets preserve shaped text instead of depending on printer code pages. Default output is **576 dots**; actual printable width/font/QR acceptance remains a paper test. `plugins.RestaurantPrinter.printableDots` in Capacitor configuration can set a multiple of eight from 384 through 832 when hardware evidence requires it. This is a build configuration, not a new cashier setting.

Only printer-class or vendor-specific interfaces with bulk OUT are offered, with explicit device selection. USB serial adapters requiring a serial protocol are not implemented. Each attempt enumerates and opens afresh, claims the selected interface, streams bounded packets, feeds four lines for manual tearing and closes. No cutter/drawer/KOT commands. This path does not use the third-party print service to send direct bytes.

Positive short USB writes advance by their actual byte count; failed/stalled writes stop without automatically resending. USB permission, decode/render, claim/disconnection and transfer failures return through the existing failed-print audit/status UI. A transfer can fail after partial paper output: check the paper before explicitly reprinting. A successful transfer reports **submitted**, never physically confirmed. Printer status/paper-out sensing is not implemented; paper-out may therefore require operator detection even if USB accepts bytes.

The isolated renderer has no Capacitor JavaScript bridge, blocks nonlocal resource requests, disables file/content access, and receives a CSP forbidding page scripts and remote assets. JavaScript is enabled solely for native readiness/layout evaluation. The HTML is removed from the plugin call options after capture and is released after the attempt. No live owner data/device or shared backups were accessed.

## Focused verification

- `npm run build:restaurant` and ESLint on the two printing modules/new browser test.
- `node --import ./scripts/project-environment.mjs --test tests/restaurant/brand-receipt.test.js`: **4 passed**.
- Focused Playwright: `DIRECT-PRINT-01`, `RECEIPT-UI-01`, `RECEIPT-ALIGN-01`: **3 passed**. Direct printing is mocked at the native bridge: exact receipt markup/logo/styles, submitted/failed/cancelled results, explicit service fallback, unchanged reprint and next bill number checked. Existing inclusive/exclusive receipt formatting and GST alignment checks retained.
- Android `assembleDebug`, `testDebugUnitTest`, `lintDebug`: pass; **16 Java tests**, including five new encoding/partial-write/failure/bounds tests. Lint: **0 errors, 20 warnings** (19 previous plus the isolated renderer's JavaScript-enable advisory).

Candidate: `artifacts/restaurant-pos-1.0.19-direct-usb-2026-11-04-debug.apk` (version 1.0.19 / 20; separately named to preserve the previous menu-options candidate). SHA-256: `dfe7eb234cc5d24b3683e5f91a594c12275f5dd3176ab1256eacdab12fea70f2`. APK signature verified and signer matches the previous 1.0.19 candidate; all **68 bundled web files** exactly match the final web build. The direct-bridge browser scenario was rerun after adding the renderer CSP; it also renders the exact isolated payload in a browser frame and verifies loaded images/fonts, no overflow and tax alignment. Native tests/build/lint were rerun after the last Java change.

This evidence does **not** verify native WebView raster capture, USB permission/lifecycle behavior or physical printing on TVS. Candidate APK is not installed. Before accepting: on TVS S6802/Android 11 with TVS RP 3230, check full receipt including Tamil/rupee glyphs, bottom of long bills, GST under RATE, logo and independently scanned merchant QR. Test permission denial, another print service holding the interface, paper-out, USB unplug/replug, printer power cycle, app restart and reboot. Verify no duplicate bill after any failure/reprint. Use an agreed sample volume; do not alter the owner's ledger for test fixtures.

API references consulted: [Capacitor app-local Android plugins](https://capacitorjs.com/docs/android/custom-code), [Android USB host](https://developer.android.com/develop/connectivity/usb/host), [Epson raster command](https://download4.epson.biz/sec_pubs/pos/reference_en/escpos/gs_lv_0.html). `GS v 0` is a legacy command whose support on this printer still needs physical confirmation; existing Android print-service fallback remains available.
