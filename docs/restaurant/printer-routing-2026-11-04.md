# RP 3230 routing correction — 4 November 2026

**Later owner evidence:** version 1.0.20 subsequently showed a native offline-asset load error before USB bytes were sent. See [the native data-resource correction](printer-asset-fix-2026-11-04.md) for 1.0.21. The initial photographs discussed below did not contain that later error.

## Evidence and cause addressed

The owner's first TVS photo shows the app detecting **RP 3230 (10927:24580, interface 0)**. These decimal identifiers are USB VID `2AAF` / PID `6004`. The second photo shows Android's **Save as PDF** destination and Letter paper. That is the separate system-print route, not evidence that native USB discovery failed. The photographs do not establish whether selecting the direct RP 3230 entry ever failed; no exact native error was supplied.

Read the local `resources/references/technical-discovery-2026-10-25.pdf`, including the full printer pages and rendered pages 4, 5 and 11. Page 5 T04 explicitly records default Android discovery failing to find the USB thermal printer. Pages 4 and 11 record the successful service path: **ESC POS USB Print Service, Looped Labs**, package `com.loopedlabs.usbprintservice`, **3 inch / 80 mm**, **203 DPI**, USB permission granted, cutter and cash drawer disabled. Its `/dev/bus/usb/007/002` address was session-specific and is not a device identifier to hardcode. The PDF proves the historical service-based print, not this APK's direct native raster path.

## Changes

- Receipt actions are explicit: **Print to USB** (Android's primary action), **Android print service**, and **Printer setup**. Desktop browser printing retains its existing action.
- Direct USB no longer offers a system-service/PDF choice in its printer selector. A single standard printer-class USB interface is selected directly; multiple or unknown vendor-specific candidates still require selection. No compatible USB interface produces an actionable USB error. No automatic fallback after a failure or partial transfer.
- Optional printer setup explains the exact PDF-proven service configuration, opens that installed app or its official listing, and opens Android Printing settings for the operator to enable it. A narrowly scoped manifest query allows checking this package on Android 11+; no broad installed-app permission.
- The explicit Android service route checks installation and enabled-service configuration before entering the print dialog. If unavailable/disabled, it shows setup and rejects the attempt, preserving the saved bill. If Android restricts the enabled-services read, an installed service is treated as unknown rather than falsely absent. Android's public print API does not let this app force a selected destination; the operator must select the configured USB service when using that optional route.
- Status now indicates an in-progress attempt instead of leaving a previous Submitted message visible while a new attempt is pending. Both print actions are disabled together. Print audit updates retain the sale captured at the start of that attempt.
- Version **1.0.20 (21)** distinguishes this update from the earlier same-version direct-USB candidate. Receipt values, HTML layout, GST calculation, SQLite, analytics and backup/restore are unchanged. Raster and USB byte-transfer code were not changed based on an unobserved error.

## Verification and limits

Focused browser checks cover independent USB/service actions, no PDF fallback following USB failure/cancellation, setup dispatch, disabled-service error, unchanged receipt content and next bill number. Existing inclusive receipt and exclusive GST-under-RATE checks are included. Test data is isolated from owner data. **4 receipt Node checks, 3 browser scenarios, 19 Java unit tests**, scoped JS lint/build and Android assemble/lint pass. Lint reports **0 errors / 20 warnings**, unchanged from the previous direct-print candidate. The direct routing scenario was rerun after adding wrapping for the receipt's printer controls; no horizontal overflow at 1280 × 720. The final APK was rebuilt with that CSS; Java source was unchanged after its passing test/lint run.

Final artifact: `artifacts/restaurant-pos-1.0.20-printer-fix-debug.apk`, also copied and hash-verified into the user's Downloads. SHA-256: `cb4e7eb680931338ad46773eb1a3118dea198225cfdd99790af4154546489cb2`. Package/version metadata confirmed: `in.vgl.restaurant`, **1.0.20 / 21**. Signature verifies and matches the previous direct-USB candidate; all **68 bundled web files** match the final build and the new native setup/guard code is present in DEX. Machine-readable record: [build verification](printer-routing-build-2026-11-04.json). Previous APKs remain preserved.

No Android device is connected through ADB. The Android 11 emulator could not start because D: has less than the project's required 5 GiB of free space; that guard was not bypassed and no owner backups/artifacts were removed. TVS native rendering, permissions, physical paper output, unplug/replug, restart and reboot remain unverified. Do not present these route changes as physical TVS acceptance. No original/CRM checkout, owner ledger or shared backup was accessed.

## Owner retest

Install the signed update over the existing app without uninstalling or clearing data. Reopen a saved bill and tap **Print to USB**; allow Android USB access if prompted. With only the connected RP 3230, this route should not open Save as PDF. Check actual paper before reprinting. If it returns an error, retain its exact message for further native diagnosis. For the historically proven service path, first use **Printer setup**, configure/enable the Looped Labs service at 80 mm / 203 DPI, then explicitly select **Android print service** and that configured destination.
