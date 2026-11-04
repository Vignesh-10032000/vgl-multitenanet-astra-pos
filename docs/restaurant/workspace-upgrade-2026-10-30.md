# Workspace visuals, offline login and shared recovery backups — 30 October 2026

This continues the existing HTML/CSS/vanilla-JS app in `D:\vgl-restaurant-pos`. It does not replace the original billing controller, GST model, final numbering or saved receipts. The earlier 1.0.3 evidence remains in `verification-2026-10-30-ui-split.md` and the nested previous build records.

## Requested result and implementation

- Sales follows screenshot 4's search/filter → icon summary cards → invoice table → pagination arrangement, using the existing navy/teal theme. It retains customer/bill search, date/payment filters, six bilingual totals, View/Reprint and Cancel/Return. The table now includes item snapshots and ten bills per page, with genuine total-count paging.
- Reports follows screenshot 5's four headline cards → revenue trend/payment breakdown → top items/summary panels arrangement. The original four detail tabs, six bilingual totals and CSV/XLSX/PDF exports are retained below the analytics. Existing date chips remain; 7/30/90-day chips are added. Custom dates open when selected; payment filtering remains directly available.
- Report cards show final revenue, bill count, average final revenue per saved bill, and original invoiced GST. GST is explicitly labelled invoiced; the app does not invent GST credit notes from monetary returns. A mixed bill contributes to Cash and GPay once, not to a third revenue channel. Negative channel totals are stated in text rather than misrepresented as positive doughnut segments.
- The lower-right reference panel is a factual cancellations/returns audit summary. This ledger has no order-type data, so no fake dine-in/takeaway/card figures or growth percentages were added.
- Dashboard adds Weekly revenue and Monthly revenue cards with local calendar/trend SVGs, visible period bounds, bilingual labels and net revenue after recorded returns. They use the current Kolkata Monday-week/month and the selected payment method independently of the dashboard's other date selection.
- Navigation, summary cards and menu rows use bundled Lucide SVGs. The product dialog uses aligned name, portion/category, price, photo and availability fields with proper spacing and touch sizes. Existing local product-photo behavior remains.
- The owner chose **username and password**. First use asks the owner to create credentials; there is no default account/password. The local access screen provides sign-in, lock, reload continuity and backup recovery. Passwords use independent random salts and PBKDF2-SHA256 with 600,000 iterations; plaintext passwords are not stored. Five failed attempts impose a 30-second wait, including concurrent attempts. Login metadata uses the existing local-preference rows, preserving schema v2 and sale snapshots.

## Backups and reinstall behavior

The Android `RestaurantBackup` plugin uses `ACTION_OPEN_DOCUMENT_TREE` to connect a user-owned shared folder. It stores persistable URI access, lists backup documents only within that folder, reads bounded files, creates new uniquely named snapshots, and never deletes backup documents. The existing print/save plugin and PrintManager route are unchanged.

After a sale, product/customer/setup change, owner setup or recorded return, a configured automatic backup creates a consistent transactional ledger snapshot plus referenced images. The saved document is read back and validated in scratch SQLite before success is shown. A write/permission/storage failure reports that the shared backup needs attention; the already-committed local sale remains saved. No configured shared folder means **no automatic external backup protection yet**; the app shows the setup status and still offers manual backups.

On recovery, the app discovers and validates the newest 20 candidate documents, skips corrupt/incomplete files and displays their date and bill count. It authenticates the owner verifier included in a chosen backup before restoring it. For pre-login backups it requires the existing current owner, or creates an owner first on a genuinely fresh installation; wrong credentials never replace sales. Backup contents are re-read and checked against the discovered checksum before replacement. Finding files alone never replaces a live ledger. Large discovered files are not retained as 20 full decoded backups in memory. Pre-login backups can be restored without removing an already-configured local owner.

**Android limitation:** shared documents remain after normal uninstall, but uninstall removes app-private data and access grants. A reinstalled app cannot silently scan arbitrary device storage. The user must choose **Find an existing backup** and reconnect the shared folder; discovery/validation then runs automatically and the saved owner's credentials allow continuation. This does not protect against the user deleting the shared folder, storage failure, or an uninstall interrupting an unfinished backup. Keep an additional copy outside the terminal.

Official basis: [Android Storage Access Framework](https://developer.android.com/training/data-storage/shared/documents-files), including shared-file survival, directory selection and persisted URI grants. Use a local Documents / Restaurant Backups folder outside Android/data. Browser preview uses the desktop folder API when available and retains the existing download/upload fallback.

The login is a **local application access lock**, not SQLite/back-up encryption or a server authentication service. Keep the device protected. Neither stored verifiers nor backups are presented as encrypted.

Recovery flushes pending cart writes before replacement and closes the serialized live SQLite connection before reloading. The installed native SQLite plugin rejects duplicate connections surviving a WebView reload, so manual and login recovery share the close/reload path. Browser restore regressions cover this ordering; physical Android acceptance remains pending.

## File map

| File | Change |
| --- | --- |
| `restaurant/reporting-ui.js` | Distinct Sales/Reports layouts, actual pagination, analytics rendering, custom and rolling dates, weekly/monthly dashboard cards. |
| `restaurant/analytics.js` | Exact selected-GST/average calculations, zero-filled/negative revenue series, local SVG bars and Cash/GPay doughnut. |
| `restaurant/workspace-icons.js` | Bundled SVG registry and shared icon markup. |
| `restaurant/workspace-style.css` | Management screen, product form, analytics, responsive and login styling within the existing theme. |
| `restaurant/index.html` | SVG navigation, Sales pager, analytics panels, shared-folder controls and owner access screen. |
| `src/vglpos/web/templates/dashboard.html` | Weekly/monthly revenue card container; original dashboard panels retained. |
| `restaurant/app.js` | Access gate, shared-backup hooks/recovery, product thumbnails, labels and existing local routes. |
| `restaurant/access.js` | Owner creation, salted password verification, serialized login throttling, session lock and backup owner reader. |
| `restaurant/access-ui.js` | First setup, sign-in/lock and authenticated recovery flow. |
| `restaurant/repository.js` | Atomic create-only/read/update helpers for existing local preference storage; sale schema/checkout retained. |
| `restaurant/backup.js` | Backup timestamp/owner validation and preservation of current owner on a pre-login restore. |
| `restaurant/backup-service.js` | Serialized append-only snapshots, provider read-back verification, discovery and guarded recovery. |
| `restaurant/backup-folder.js` | Native bridge and desktop directory-handle transport with size/permission checks. |
| `android/app/src/main/java/in/vgl/restaurant/RestaurantBackupPlugin.java` | Shared folder selection, persistent permissions, confined discovery/read/write and lifecycle-safe worker. |
| `android/app/src/main/java/in/vgl/restaurant/MainActivity.java` | Register the backup plugin; existing print plugin preserved. |
| `android/app/build.gradle` | Version 1.0.4 (5). |
| `tests/restaurant/access-analytics-backup.test.js` | Password/throttling, old backup/owner preservation, exact chart summaries and simulated shared-folder recovery/failures. |
| `tests/restaurant-browser/workspace-upgrade.spec.js` | Login, reference-style layouts, charts, actual page navigation, revenue cards, responsive overflow and product field geometry; screenshots. |
| `tests/restaurant-browser/access-helper.js` | Configure credentials in disposable test contexts only. |
| Existing browser suites and `scripts/profile-restaurant.mjs` | Sign into disposable test data and account for real Sales pagination. |
| `AGENTS.md`, root handoff/status files, build record | Preserve the owner's current requirements and new evidence for future work. |

## Verification and device limits

Fresh `npm test`: **53 passed** (11 preserved frontend checks, including 200 tax-parity cases; 42 restaurant checks). JavaScript lint and restaurant web build passed. The limited four-rule security scan reported zero findings across 39 files. Final Playwright run: **21 passed**, including all earlier billing/split/exports regressions and the new login/layout checks.

**Android build VERIFIED:** `scripts/build-restaurant-android.ps1 -SkipWebBuild -Lint -UnitTests` passed. Lint: **0 errors, 19 warnings**. All **5 Java tests** passed earlier on the same unchanged native source (four DocumentWriter checks and one scaffold check); the final web-only rebuild reused those results. An earlier lint failure on the SAF permission flags was corrected; the final build/lint run passed without suppressing the check.

Debug candidate: `artifacts/restaurant-pos-1.0.4-debug.apk`, version **1.0.4 (5)**. Its v2 signature was verified with apksigner 36.1.0, package/version/ABIs with aapt, and every built web file was compared to the APK bytes. Exact size, SHA-256 and per-asset hashes are in [build-verification.json](build-verification.json); all previous build records and APKs are retained. Logs: `.tools/workspace-upgrade-android-final.log`, `.tools/workspace-upgrade-apk-signature.log`.

Screenshots: `test-results/workspace-upgrade/` contains login desktop/phone, Sales, Reports, dashboard revenue and product form. Browser tests use disposable accounts and ledgers; the user's localhost data and credentials were not configured or replaced by tests.

**NOT VERIFIED on a physical device:** Android folder-picker/provider behavior, uninstall/reinstall and grant re-selection, native cold restart, TVS/OnePlus performance, password derivation speed on the TVS, and physical receipt/reconnect/paper-out/Tamil/QR output. No device/emulator is attached. App-private live SQLite is still removed by uninstall; only successfully completed shared backups survive. This is not production acceptance.
