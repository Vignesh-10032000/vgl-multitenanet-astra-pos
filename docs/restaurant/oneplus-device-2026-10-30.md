# OnePlus phone verification and fixes — 30 October 2026

**Performance scope:** these are functional phone checks. The governing optimization target is the TVS S6802 using `tvs-performance-baseline.md`; do not transfer this phone's timings, RAM headroom or storage behavior to the TVS.

Device: OnePlus 9R / LE2101, Android 14 (API 34), Android System WebView 155.0.8059.43. Connected through authorized USB ADB. No root, app-data clearing or uninstall was used.

## Installed candidate

Latest: `artifacts/restaurant-pos-1.0.6-debug.apk`, package `in.vgl.restaurant`, version 1.0.6 (7). SHA-256: `46a7b63c83dc588ae0b943ca1e9c2604380dac0c76e3623b3ca6d994343090c6`. All 23 web assets match the current build byte for byte. Android Debug signature verified using apksigner 36.1.0. Older APKs remain preserved. Updates used `adb install -r`; no app data was cleared and no uninstall was performed.

## Physical-device evidence

- First installation and native SQLite initialization succeeded. The owner created their own username/password directly on the phone and signed in after updates and a cold process restart. Credentials were not entered into scripts or shared in chat.
- All seven navigation destinations were exercised through Playwright attached to the physical WebView. Actual landscape viewport: 900 × 383 CSS pixels. No horizontal page overflow or page errors occurred in that navigation run. Initial and final screenshots are under `test-results/android-oneplus/`.
- Native Cash, GPay and mixed-tender checkouts saved ₹170 each with taxable value ₹161.90 and CGST/SGST ₹4.05 each. Cash ₹200 tendered produced ₹30 change. Split tender was Cash ₹50 + UPI ₹120. These three bills have customer `DEVICE TEST - NO REAL PAYMENT` and were fully voided with device-test audit reasons; no actual settlement is claimed.
- The owner's bill `AR/2627/000001` for ₹870 remains saved. Test bills `000002`–`000004` remain cancelled, giving four bills, ₹1,380 gross, ₹510 corrections and ₹870 final sales. No saved bill or audit record was deleted. The original four-item cart had already been completed by the owner before the checkout test started; the checkout test began with an empty draft.
- The owner granted SAF access to the shared `PC` folder. Choosing the folder created a 19,211-byte complete backup, read-back/validation succeeded, and Find backups discovered the candidate with all four bills. A consistent shared document was used; the live SQLite file was not copied.
- With Wi-Fi and mobile data off and Android reporting `Active default network: none`, the app was force-stopped and launched again. After owner sign-in, all four bills, balances, a temporary unpaid ₹170 draft and the shared-folder grant survived. The temporary draft was then removed, returning the cart to empty. Android's `navigator.onLine` remained true due to its connectivity reporting, so the offline evidence is the device radio/default-network state, not that browser flag.
- CSV, XLSX and PDF were generated offline and saved through Android's system document picker into the selected folder. The exported CSV contains four invoices and three corrections. XLSX was reopened with ExcelJS: four invoices, five tender rows, seven item rows and three corrections; its summary matches gross ₹1,380, corrections ₹510 and net/cash ₹870, UPI ₹0. The 1,417,583-byte PDF contains 11 pages; it was parsed with pypdf, rendered with Poppler, and visually inspected using a contact sheet and the full first page. Native export artifacts and evidence are local under `test-results/android-oneplus/`.

## Bugs reproduced and corrected

1. **Short landscape sidebar:** Settings was below a 383px-tall sticky sidebar with no scrolling. A real Playwright click timed out because it remained outside the viewport. `restaurant/workspace-style.css` now permits vertical sidebar scrolling above the existing portrait breakpoint and preserves child sizes. `PHONE-NAV-01` reproduces the old failure and passes after the fix in both browser/native styling; billing arrangement and money logic are unchanged.
2. **Native PDF crash:** the old picker call retained base64 PDF bytes in its options. Capacitor serialized them twice into activity saved state when the picker stopped the app: `TransactionTooLargeException`, parcel size 7,681,120 bytes. Version 1.0.6 stages bytes in app-private cache, removes the payload from call options before launching any activity, and retains only a small opaque token. The callback streams the staged file into the document provider and reports success after closing the provider stream. Cancellation/error removes only that staged cache file; shared backup documents are untouched. A real repeat of the PDF picker/save succeeded, kept the process alive and left its staging directory empty. The old failed PDF left a zero-byte document; successful saves use Android's collision-safe names without overwriting prior files.

`StagedDocuments.java` contains token/path checks and staged export copy/cleanup. `RestaurantDocumentsPlugin.java` coordinates asynchronous staging and the picker callback. The PrintManager receipt route was not changed. Six new `StagedDocumentsTest.java` checks cover a 3 MB payload, cancellation, provider write/close failures, missing cache/provider streams and rejection of tokens targeting other files.

## Verification

- Browser suite: **22 passed** (`.tools/oneplus-browser-final-green.log`); new landscape case was demonstrated red before the CSS fix and green afterward. Its initial draft assertion was corrected to wait for the existing asynchronous price calculation before taking a snapshot.
- Native unit tests: **11 passed**, freshly executed for the new native source (four existing DocumentWriter tests, six StagedDocuments tests, one scaffold test).
- Android assemble and lint: passed, **0 errors / 19 warnings** (`.tools/oneplus-android-106.log`). JavaScript lint passed. The scoped four-rule Semgrep scan passed with zero findings. Existing 53 Node checks cover the unchanged business logic; they were not rerun for this CSS/native-only follow-up.
- Build/signature/asset hashes: `docs/restaurant/build-verification.json`. Local device evidence: `navigation.json`, `billing.json`, `backup-discovery.json`, `restart.json`, exported documents and rendered PDF pages in `test-results/android-oneplus/`. Before-fix crash evidence: `.tools/oneplus-pdf-crash.txt`.

## Remaining acceptance

Actual uninstall/reinstall recovery, process death while a picker is open, other document providers, TVS S6802 Android 11 performance and physical receipt/Tamil/QR/USB reconnect printing remain **NOT VERIFIED**. Shared documents remain outside app-private storage, but reinstall requires reconnecting the folder and authenticating before restore; no uninstall of this owner's data was attempted. These results do not establish production acceptance.
