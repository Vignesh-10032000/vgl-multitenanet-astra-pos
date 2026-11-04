# Native receipt data-resource correction — 4 November 2026

## Owner evidence

The new TVS photos show version 1.0.20 and a direct-path failure behind Printer setup: **"Could not load an offline receipt asset; no USB bytes sent."** A separate photo shows the optional Android-service preflight reporting its service is unavailable. These are different paths. The direct renderer failed before opening/sending the USB job; installing the optional service is not required to fix that native asset error.

## Defect and scoped correction

The native `ReceiptRaster` client only forwarded URLs beginning with the app's localhost origin. Every other request received an empty `text/plain` response. Android's [WebViewClient contract](https://developer.android.com/reference/android/webkit/WebViewClient#shouldInterceptRequest(android.webkit.WebView,%20android.webkit.WebResourceRequest)) explicitly includes **data:** URLs in `shouldInterceptRequest`, not just network requests. The generated receipt contains embedded logo/QR images and the renderer loads an HTML document with `loadDataWithBaseURL`; rejecting embedded resources is a concrete error in this filter. Version 1.0.20 did not record which exact URL failed, so that individual request cannot be recovered from its generic status photo.

Version **1.0.21 (22)** uses an explicit, tested policy:

- Embedded `data:` resources return **null** from the interceptor, allowing WebView to decode their existing bytes.
- Bundled CSS, fonts and images at the exact app origin continue through Capacitor's offline asset server.
- Other hosts, device files, content URIs and script/blob requests remain blocked. Rejections use HTTP 403 rather than a false successful empty resource.
- Native errors now include the Android/HTTP error code and a bounded asset filename, never the base64 payload or full private device URL. This makes any remaining device failure diagnosable.
- The receipt document explicitly declares UTF-8. Receipt HTML layout, original image bytes and URLs, saved monetary snapshots, payment/GST calculations, SQLite, analytics and backup/restore are unchanged.

There is no new printing dependency and no automatic fallback/retry. A failed render still sends no USB print bytes and does not create a sale. The 1.0.20 direct/service separation remains in place.

## Verification and remaining acceptance

Three new Java regression tests cover embedded document/JPEG/PNG/SVG/font URLs, local CSS/font/logo URLs, trailing-origin slash handling, and rejection of unrelated/forged hosts and device files. **22 Java tests, 4 receipt Node checks, scoped JS lint/build and Android assemble/lint pass (0 errors / 20 warnings).** Three distinct focused browser scenarios pass: direct routing and GST alignment passed in the broad run; the historical receipt/reload case initially failed after reload, was corrected to await the existing startup-ready helper, and passed on rerun. No application startup code was changed for that test wait. Browser tests do not execute Android's WebViewClient.

Final APK: `artifacts/restaurant-pos-1.0.21-usb-asset-fix-debug.apk`, also copied/hash-verified in Downloads. SHA-256: `379924522bdccfb4653b67564c0ff0127dce1c837dee5bec1a86f0c30bafa4d1`. Package metadata confirms `in.vgl.restaurant`, version **1.0.21 / 22**. Signature verifies and matches 1.0.20; all **68 bundled web files** match the final build, and the new resource-policy code is present in DEX. See [machine-readable build evidence](printer-asset-build-2026-11-04.json). Earlier APKs are retained.

No Android device is connected through ADB. The earlier Android 11 emulator attempt was blocked by the project's 5 GiB free-space guard; available D: space remains below it. That guard was not bypassed. No owner device, account, ledger, original/CRM checkout, shared backup or earlier APK was changed. Native rendering and physical TVS paper output remain to be retested after installing this update in place. Use a saved bill → **Print to USB** and retain any new exact error text. Do not uninstall or clear data for this test.
