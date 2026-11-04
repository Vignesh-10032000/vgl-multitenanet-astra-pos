# Native receipt asset correction — 4 November 2026

Candidate **1.0.21 (22)** fixes the native filter rejecting embedded `data:` receipt/logo resources. Owner photos of 1.0.20 showed **"Could not load an offline receipt asset; no USB bytes sent."** See [the correction report](docs/restaurant/printer-asset-fix-2026-11-04.md) and its build record. Verified: 22 Java tests, 4 receipt Node checks, 3 distinct browser scenarios (reload case corrected to wait for startup and rerun), JS lint/build and Android assemble/lint (0 errors / 20 warnings); same signer and 68 matched web assets. APK copied to Downloads. **Not installed/device-tested here; physical TVS printing remains pending.** No owner ledger/shared backup was accessed. Earlier routing/service separation remains; optional service installation does not fix the native resource bug.

---

# RP 3230 print routing — 4 November 2026

Source/candidate **1.0.20 (21)** separates **Print to USB** from the optional Android print-service/PDF panel and adds **Printer setup** using the PDF-proven Looped Labs service configuration. Owner photos confirm native RP 3230 detection and a separate Save as PDF panel; they do not establish a direct USB transfer failure. See [the scoped correction report](docs/restaurant/printer-routing-2026-11-04.md). Focused checks: 4 receipt Node tests, 3 browser scenarios, 19 Java tests; JS lint/build and Android assemble/lint pass (0 errors / 20 warnings). **Not installed or physically verified on TVS.** No owner ledger/shared backups were accessed; native rendering/USB/reconnect acceptance remains pending.

---

# Regular / Parcel and fixed kilogram portions — 3 November 2026

Source/candidate **1.0.19 (20)** adds Regular / Parcel selection to Add/Edit Product, matching filters on Products/Billing, and optional fixed kilogram portions with independent prices changed through Edit. Historical bills, prices and images are preserved. See [the menu-options report](docs/restaurant/menu-options-2026-11-03.md) and its build record.

Verified: 103 Node checks, all 62 distinct browser scenarios (61 full-run passes plus corrected startup-wait GST rerun), JS lint/build, security scan (55 files / four rules / zero findings), Android build/lint (zero errors / 19 existing warnings), same signer as 1.0.18, and all 67 bundled web files. **Not installed or device-tested.** No owner device/ledger/credentials/shared backups were accessed. Last documented installed version remains 1.0.18; TVS/physical-print/native lifecycle acceptance is pending.

---

# Current device state — 1.0.18 verified on Pad Go

The corrected production 1.0.18 (19) is installed; the owner signed in privately. Billing is left open with an empty cart in English/light mode. Nine real bills and every original business/account/settings row remain unchanged; no live test sale was created. All 23 images and 15 existing shared backups were preserved. Full browser suite: 60 passed; lint passed. The earlier unsafe polish APK remains WITHDRAWN. Read [the final device/report checkpoint](docs/restaurant/padgo-polish-verification-2026-11-03.md), including A6's retained in-memory WASM validation exception and unverified TVS/release/physical-print/portrait cases. Prior pause/install notes below are historical.

---

# Resumed verification — 3 November 2026

The owner requested continuation after the safe pause. The corrected 1.0.18 APK has the production package ID, matches the previous signer, and all 67 bundled web files match the current build. Wireless ADB is currently disconnected; the previous endpoint refuses connections and no device is discovered. The current Wireless debugging **IP address & Port** is needed. No live-device changes have occurred in this resumed session. Prior pause/recovery details remain below and in [the device handoff](docs/restaurant/padgo-polish-verification-2026-11-03.md).

---

# Safely paused at the owner's request — 3 November 2026

Read [the pause and recovery handoff](docs/restaurant/padgo-polish-verification-2026-11-03.md) before continuing. Nine real bills were recovered and exactly verified; the previous known APK was restored. Fixed production 1.0.18 is built but NOT installed. The unsafe polish APK is withdrawn. Wireless ADB disconnected at pause, so current tablet screen/process state and rotation restoration could not be rechecked. Test runners have stopped; source fixes and private recovery evidence are preserved. Resume only when the owner requests it. Earlier reports below are historical and superseded where they conflict.

---

# Critical Pad Go verification update — 3 November 2026

The first startup-polish 1.0.17 (18), SHA-256 `fce41f78ef1cadd5c0f2e30e3ca0a76db2a14ddf9ea21e2ce17e3fc89eadc804`, is WITHDRAWN. On the physical Pad Go, inspecting a synthetic backup through its new native validation path replaced the live ledger before confirmation. This path has been disabled and the previous isolated in-memory sql.js backup validator restored. Native SQLite remains the authoritative billing database. A6's request to exclude WASM from native backup validation is therefore not fulfilled.

All nine real owner bills / 25 lines / ten payments, customers, credentials/settings and 23 images were recovered from the verified latest shared backup and matched every table against the captured owner snapshot. Failure evidence and consistent closed-app recovery archives remain private under `test-results/padgo-polish-2026-11-03-1793674858462/`. The owner-created ninth bill occurred during sign-in, not from the assistant's unpaid tests. All 14 original backups remain; the owner's ninth bill appended a fifteenth. No shared backup was deleted.

The known previous APK was put back in place while 1.0.18 (19) is prepared. The recovered owner database is stopped and intact. A separate package `in.vgl.restaurant.polishcheck` has passed different-ledger inspection/cancel without changes, corrupted-checksum rejection, and explicit confirmed restore of complete images. Final fixed-APK installation evidence will be recorded in `docs/restaurant/padgo-polish-verification-2026-11-03.md`. Do not reinstall the withdrawn artifact.

---

# OnePlus Pad Go updated — 3 November 2026

Owner-requested in-place installation of **1.0.17 (18)** completed over wireless ADB on OnePlus OPD2305 / Android 14. Installed APK hash matches the verified artifact. Closed-app safety archives confirm all 43 protected files unchanged before startup; after native schema-v3 migration, original business rows, images and account preferences are preserved (seven bills / 16 sale lines / eight payments / 36 products). SQLite integrity and foreign-key checks pass. App is open at existing owner sign-in; no sale, credential reset, live restore or shared-backup deletion. Details: `docs/restaurant/padgo-install-2026-11-03.md`. Signed-in billing, TVS performance, physical printing and actual reinstall recovery remain unverified for this update. Preserve private safety artifacts locally. Older installation statuses below are historical.

---

# GST figures under RATE and counter optimization — 2 November 2026

Latest source/candidate: **1.0.17 (18)**, `artifacts/restaurant-pos-1.0.17-debug.apk`, also copied and hash-verified in Downloads. Owner confirmed GST rupee figures directly beneath RATE; the receipt now uses shared columns for discount/tax/rounding alignment. ₹170 + ₹4.25 CGST + ₹4.25 SGST = ₹178.50 remains unchanged. Original images, saved bills and v3 accounting/backup behavior are preserved.

Counter changes remove the fixed quote delay and redundant render, refresh a reusable settings snapshot on billing refresh, share duplicate immutable image reads and bound retained image payload to 8 MiB. Desktop diagnostic: 1,000 bills/22 photos, median tap-to-total paint 418 → 245.1 ms; renders 2 → 1; warm image reads 37 → 23. Warm startup speedup was NOT established. These are desktop-only measurements, not TVS acceptance. Read `docs/restaurant/receipt-performance-2026-11-02.md` and the build record.

Verified: **96 Node checks / 41 browser scenarios** (40 broad passes plus corrected logo-save-wait test passing separately), lint/build, scoped security (51 files / four rules / zero findings), Android assemble/lint (zero errors / 19 existing warnings), signature and 58 matched web assets. Eleven unchanged Java tests reused passing cached results. The 80 mm PDF was rendered/visually checked. **Not installed**: no TVS is detected; owner device/ledger/credentials/shared backups were untouched. Native TVS performance, lifecycle/migration, physical printing and actual reinstall recovery remain pending. Earlier records below are historical.

---

# Menu prices exclude GST — 2 November 2026

Owner correction: add **CGST 2.5% + SGST 2.5%** to the restaurant menu base prices for NEW bills. **₹170 + ₹4.25 + ₹4.25 = ₹178.50** before configured rounding (default off). This supersedes earlier inclusive-price statements for future billing. Keep historical inclusive bills, identities, taxes/payments and menu base prices unchanged. Inclusive/exclusive basis is editable and snapshotted per sale; v3 database/backup support retains v1/v2 backup compatibility. Read `docs/restaurant/gst-exclusive-2026-11-02.md`.

Latest source/candidate: **1.0.16 (17)**, `artifacts/restaurant-pos-1.0.16-debug.apk`. **92 Node checks / 38 browser scenarios verified** (37 broad-run passes plus corrected photo test; both new GST cases also rerun), JS lint/build, SymPy/1,500 generated exclusive cases, security (50 files / four rules / zero findings), Android assemble/lint (zero errors / 19 existing warnings), signature and 58 byte-matched web files. Eleven unchanged native Java tests reused passing cached results. Original photos, branding, language/theme controls and all prior local work remain.

**NOT INSTALLED:** TVS still absent from Windows/ADB after the owner's USB-debugging/replug attempt. No owner device, live ledger, credentials or shared backups were accessed or changed. Last documented installed OnePlus version remains 1.0.14 (15); TVS installed state is unknown. Native v3 migration, TVS lifecycle/performance, physical printing and actual reinstall recovery remain unverified. An older APK cannot open a v3 ledger; never clear data to bypass that check. Prior records below are historical.

---

# Top-bar Tamil/English and dark mode — 2 November 2026

Latest source/candidate: **1.0.15 (16)**, `artifacts/restaurant-pos-1.0.15-debug.apk`. Added the owner-requested Tamil/English and moon/sun controls to the current top bar. Both display preferences persist locally; dictionaries/fonts ship offline. Billing arrangement, saved ledger and original menu photos are preserved. Details: `docs/restaurant/preferences-2026-11-02.md` and `docs/restaurant/build-verification.json`.

Fresh **87 Node checks / 36 browser scenarios**, JS lint/build, security scan (50 files / four rules / zero findings), Android assemble/lint (zero errors / 19 existing warnings), signature and all 58 packaged assets passed. No native Java changes; native unit tests were not rerun for this display change. **1.0.15 has not been installed or device-tested in this chat.** Last documented installed version remains 1.0.14 (15). Browser checks used disposable fixtures; owner device data, credentials, shared backups and installed state were not accessed. TVS, physical printing and actual reinstall recovery remain pending. Prior records below are historical.

---

# Original food photos restored — 2 November 2026

Latest source/installed APK: **1.0.14 (15)**, `artifacts/restaurant-pos-1.0.14-debug.apk`. Owner rejected the newer web food photos and explicitly requested the old pictures. Read `docs/restaurant/menu-photo-restore-2026-11-02.md`. All 36 menu entries now use the original v1 illustrations, with full uncropped display. Fresh installations skip the v2 photo update. Existing v2 installations revert only matching bundled references once under **local:bundled-menu-photos-v3-illustrations**; preserve v1/v2/v3 markers, owner uploads, explicit removals, renamed dishes and all source assets. Restaurant name/new Arafa logo, VGL slogan, dotted receipt rules, prices and inclusive GST are unchanged.

Fresh **87 Node checks / 31 browser scenarios**, lint/build, security (48 files / four rules / zero findings), Android build/lint (0 errors / 19 existing warnings), signature and all 58 packaged assets passed. Eleven unchanged native tests reused cached passing results. **1.0.14 is installed on the connected OnePlus OPD2305 and left signed in on Billing, All menu.** All 36 rendered photo data URLs and image decodes match original v1 bytes; original grills and full image backup verified.

All **seven bills / 16 item rows / eight tenders**, credentials/preferences and empty cart are retained. All 11 prior shared backups remain and a new complete image backup was appended, giving **12 backups**. No uninstall, data clear, live restore, native test sale or backup deletion. Installed APK bytes match the artifact. Private preservation snapshots stay local. TVS performance, physical printing and actual uninstall/reinstall recovery remain pending. Earlier version records below are historical.

---

# Restaurant identity, subtle VGL credit and physical Android update — 2 November 2026

Current installed APK/source: **1.0.13 (14)**, `artifacts/restaurant-pos-1.0.13-debug.apk`. Read `docs/restaurant/vgl-branding-2026-11-02.md` and `build-verification.json`. Restaurant name **Arafah Briyani Restaurant** and the approved new **Arafa badge without Biryani inside the badge** remain primary on sign-in/sidebar. The supplied VGL logo is an identical local copy in a smaller secondary credit, with **Build · Automate · Grow** below it. Compact phones no longer hide the restaurant badge; identity is rendered before optional photos. Actual tablet testing corrected a clipped login slogan. Browser/Android launcher icons use a blue cloche-and-receipt vector recreation of the supplied reference.

Fresh **83 Node checks, 31 browser scenarios**, JS lint/build, scoped security scan (47 files / four rules / zero findings), Android build/lint (0 errors / 19 existing warnings), signature and all **58** bundled web files passed. Eleven unchanged Java tests reused cached passing results. **1.0.13 is installed and open on Billing on the physical OnePlus OPD2305, after private owner sign-in.** Installed APK bytes match the artifact; native restaurant/logo/VGL layout, all seven navigation links and data retention were checked at 1070 × 716.

Preserve all **seven bills / 16 item rows / eight tenders / 11 shared backups** and owner credentials. The owner completed the previous ₹540 three-item draft as **AR/2627/000007** during this session; the current cart is empty. This was owner activity, not an assistant-generated test sale. Each in-place install preserved closed-app archives/table contents exactly; no uninstall, data clear or live restore occurred. Earlier default-logo/photo markers and immutable sales remain protected. Private safety archives/database snapshots are local evidence: do not upload them. Physical printing, TVS performance and actual uninstall/reinstall recovery remain unverified. Older version records below are historical.

---

# Dotted receipt rules and sourced menu photos — 1 November 2026

Latest candidate: **1.0.11 (12)**, `artifacts/restaurant-pos-1.0.11-debug.apk`. Read `docs/restaurant/menu-refresh-2026-11-01.md` and `build-verification.json`. Owner requested dotted rules under each food item, full uncropped thumbnails and matched internet photos, especially grills. Ten attributed Wikimedia photographs now replace only the known v1 illustrations for 21 menu entries; 15 entries retain earlier illustrations. All thumbnails show their full source composition. Settings includes offline photo credits and the APK distributes attribution. Preserve **both** `local:bundled-menu-photos-v1` and `local:bundled-menu-photos-v2`; never reset markers to refill removed photos. Existing uploads, removals, renamed products, prices, inclusive GST and saved sales remain protected.

Fresh **83 Node checks / 30 browser scenarios**, JS lint/build, scoped security scan (46 files / four rules / zero findings), Android build/lint (0 errors / 19 existing warnings), signature and all 57 packaged assets passed. Eleven unchanged Java tests reused cached passing results. Three-item 80 mm PDF and menu/grill screenshots were rendered/visually reviewed. **1.0.11 is not installed or physically printed**; no adb device is connected. Localhost is serving at http://127.0.0.1:5174/#billing. Preserve owner data/credentials/draft, append-only shared backups, source assets and previous APKs. Earlier version records below are historical.

---

# Receipt and logo update — 1 November 2026

Latest source/candidate: **1.0.10 (11)**, `artifacts/restaurant-pos-1.0.10-debug.apk`. Read `docs/restaurant/receipt-brand-2026-11-01.md` and `build-verification.json`. Owner requested their current receipt layout and replacement badge with **Biryani removed from the logo**. Receipt now follows that hierarchy on 80 mm paper. The configured restaurant name and confirmed inclusive GST are unchanged. New local logo is installed once into the existing ImageStore/settings with `local:owner-brand-logo-v2`; preserve uploads, removals, old sale identities and complete backup images. Do not reset the marker or rewrite historical sales. Original source/edited master are retained under `resources/branding/2026-11-01/`.

Fresh: **79 Node checks, 29 browser scenarios**, JS lint/build, scoped security scan (45 files/four rules/zero findings), Android build/lint (zero errors/19 existing warnings), signature and all 46 bundled asset matches passed. Eleven unchanged Java tests reused cached passing results. The exact ₹169 reference example and one-page 80 mm print PDF were rendered/visually reviewed. No Android device is currently connected; **1.0.10 has not been installed or physically printed**. Older version/device reports below are historical. Preserve all local work, owner data/draft/credentials, menu photo marker, append-only shared backups and previous APKs.

---

# Reliability audit — 31 October 2026

Read `TEST_PLAN.md` and `TEST_REPORT.md`. One reproduced invalid-discount checkout default was corrected with regression coverage. Final: 75 Node checks, 27 browser scenarios, 11 freshly executed Java tests pass; 100/500/1,000-bill isolated desktop stress and 50-bill actual OnePlus SQLite bridge checks pass. Owner tables/draft and all nine shared backup metadata hashes matched before/after. Three named `audit_*` synthetic database files were closed and retained on the phone, separate from business data.

Distinct signed candidate `artifacts/restaurant-pos-1.0.9-audit-debug.apk` was built/asset-verified but **not installed**. The owner's installed 1.0.9 and visible ₹340 unpaid draft/demo QR remain unchanged. Existing 19 Android Lint warnings and 13 moderate dependency nodes remain open. TVS endurance, physical printing, actual reinstall/SAF recovery and newly built APK installation acceptance remain unverified. Preserve all earlier work, bundled-photo markers and backups.

---

# GPay QR demo update — 31 October 2026

Current APK/source: **1.0.9 (10)**, `artifacts/restaurant-pos-1.0.9-debug.apk`. Read `docs/restaurant/gpay-qr-2026-10-31.md` and `docs/restaurant/build-verification.json`. Owner requested a mockup because merchant UPI details are not available. Billing → Pay → GPay or split → Show GPay QR displays the exact GPay share. Without verified merchant setup it clearly says DEMO · NO PAYMENT and encodes non-payment text; no sample account or merchant settings are installed. Viewing/closing QR never saves a bill. Existing Settings can enable the merchant branch later, with manual receipt confirmation. No gateway/automatic settlement verification was added.

Verified: 61 Node checks (50 restaurant), 26 browser scenarios, independently decoded QR PNGs, JS lint/build, scoped security scan (44 files/four rules/zero findings), Android build/lint (zero errors/19 warnings), 11 unchanged native tests reused passing cached results, signed APK and 45 byte-matched assets. Physical OPD2305 follow-up passed after private owner sign-in: full ₹340 demo and Cash ₹50 / GPay ₹290 split demo rendered offline and decoded independently as non-payment text. All six bills and related item/tender/correction rows, all 36 products/photo references, the original two-item ₹340 unpaid draft, empty merchant settings and all nine shared backups in Pos matched the pre-update snapshot. No sale or bill number was created by viewing the QR. The full demo is left visible over the unchanged draft for the owner. Evidence is in `test-results/payment-qr-device/`; `.tools/opd2305-qr-check.mjs` is retained as the completed check, not a task to rerun against a stale snapshot after owner edits. Preserve all data, credentials, earlier cancelled tests and append-only backups. The previous 1.0.8 physical report below is historical and remains valid for that version. Real merchant payment, TVS performance, physical printing and actual uninstall/reinstall recovery remain unverified.

---

# Menu photo update — 31 October 2026

Current source/debug candidate: **1.0.8 (9)**, `artifacts/restaurant-pos-1.0.8-debug.apk`. Read `docs/restaurant/menu-photos-2026-10-31.md` and `build-verification.json`. Added 22 illustrative generated food photos for the 36 original menu entries: JPEGs total 947,459 bytes, maximum edge 384px, bundled offline. Existing uploads and renamed/changed-portion products are protected; image references plus `local:bundled-menu-photos-v1` are installed once in one transaction after files are ready. Preserve that marker so explicit removals do not refill on restart. Complete backups contain the image bytes and marker. Prices, inclusive GST, historical sales and billing arrangement remain unchanged. Source originals/prompts are retained under `resources/menu-photos/`; optimized runtime files are `restaurant/public/menu-photos/v1/`. Do not regenerate or recreate completed assets unnecessarily.

Verified: 58 Node checks (47 restaurant), 24 browser scenarios, JS lint/build, scoped security scan (42 files/4 rules/zero findings), Android build/lint (0 errors/19 warnings). Eleven unchanged native tests reused passing results. Signed APK checked; all 45 web assets match. Localhost is running at http://127.0.0.1:5174/. Physical OPD2305 follow-up: **1.0.8 is installed and tested offline**; read `docs/restaurant/opd2305-device-2026-10-31.md`. All 36 photo references/22 local images, Cash/UPI/split and audited cancellations, restart with the owner’s two-item ₹340 draft, shared-folder access/discovery, complete image backup and CSV/XLSX/PDF saves passed. The original three bills and ₹1,735 net remain unchanged; preserve the three cancelled test bills and all nine shared backups in Pos. The image-including backup also restored exactly into a disposable database. Earlier OnePlus 9R/Samsung reports retain their listed versions. Actual TVS performance and physical printing remain pending; native photo upgrade from an older installed APK and actual uninstall/reinstall recovery were not tested. Preserve all local work, credentials and backups.

---

Latest Samsung follow-up: **1.0.7 (8)** is installed; see `docs/restaurant/samsung-device-2026-10-30.md` and `build-verification.json`. The same 1.0.6 baseline passed native Cash/GPay/split, audited cancellations, offline restart, shared-backup save/discovery and CSV/XLSX/PDF tests on Samsung SM-A235F. The Samsung's tighter 732 × 336 viewport exposed clipped navigation labels; the compact-sidebar fix is browser-verified (23 scenarios) and previewed on the physical phone. Android build/lint passed, 0 errors/19 warnings; 11 unchanged Java tests reused passing results. The final installed 1.0.7 phone check passed after private owner sign-in: all seven navigation links/labels fit the sidebar, the three cancelled test bills and zero net balance are intact, all eight shared backups remain, and the cart is empty. Preserve its three cancelled device-test bills, owner account and eight shared backups in Music; mobile data was restored to its original enabled state. OnePlus remains last tested on 1.0.6. TVS remains the governing performance target; neither phone establishes TVS readiness.

# Phone verification update — 30 October 2026

**Governing performance target: TVS S6802, not the OnePlus.** Use the collected TVS hardware evidence and constraints in `docs/restaurant/tvs-performance-baseline.md`. Phone results below establish functional checks only; actual TVS measurements are required for performance acceptance.

Latest installed candidate: **1.0.6 (7)** at `artifacts/restaurant-pos-1.0.6-debug.apk`. Read `docs/restaurant/oneplus-device-2026-10-30.md` and `docs/restaurant/build-verification.json` first. OnePlus 9R / Android 14 checks covered owner login, native Cash/GPay/split bills, audited cancellations, offline process restart with saved bills and draft, shared-folder backup save/discovery and native CSV/XLSX/PDF saves. Device tests exposed and corrected a short-landscape sidebar navigation bug and a PDF picker `TransactionTooLargeException`; all 22 browser scenarios and 11 native unit tests pass, Android build/lint passes (0 errors, 19 warnings), and the scoped security scan reports zero findings. Existing 53 Node checks cover unchanged business logic.

The physical phone now contains the owner's saved bill `AR/2627/000001` for ₹870 and three cancelled device-test bills (`000002`–`000004`, customer `DEVICE TEST - NO REAL PAYMENT`). Preserve these records, credentials and the user-selected shared `PC` backup folder. No app data was cleared or uninstalled. Native testing used no default internet network. Physical printing, TVS S6802 acceptance, process death while a picker is open and actual uninstall/reinstall restore remain unverified. Earlier statuses below are historical; preserve confirmed inclusive GST and all local work.

---

# Latest workspace result — 30 October 2026

Sales/Reports have been restyled from the owner's references in the current theme, with weekly/monthly revenue cards, aligned product forms and SVG navigation. Offline username/password owner setup and shared-folder automatic backups/recovery are implemented. See docs/restaurant/workspace-upgrade-2026-10-30.md and docs/restaurant/build-verification.json. Fresh checks: 53 Node tests, 21 browser scenarios, 5 Java tests passed; lint/build passed; Android Lint 0 errors/19 warnings. Signed debug candidate: artifacts/restaurant-pos-1.0.4-debug.apk (1.0.4 / 5), with all 23 bundled files matched.

First use requires creating the owner's own credentials; there is no preset password. Choose a shared backup folder in Settings to enable external automatic backups. Shared documents remain after normal uninstall, but reinstall requires reconnecting the folder before automatic discovery and authenticated recovery. Real Android uninstall/reinstall/provider/lifecycle and TVS/printer acceptance are still unverified. Preserve all current local work, inclusive GST and immutable sales. Do not reset app data to bypass login. Earlier checkpoints below are historical.

---

# Current result — 30 October 2026

The existing UI/report/split-payment work is implemented and desktop-verified: 48 unit/frontend checks, 19 browser scenarios, lint and restaurant build passed. Read docs/restaurant/verification-2026-10-30-ui-split.md and build-verification.json for the latest evidence and APK record. Preserve this checkout and all local work. The handoff below records the earlier unfinished checkpoint; its red browser status is historical. Physical Android/TVS/printer acceptance remains pending.

---

# Restaurant POS — start here

Updated 30 October 2026. The owner requested a new chat under this **same project**; this handoff does not create another chat.

1. Read AGENTS.md, HANDOFF.md and NEW_CHAT_PROMPT.md.
2. Read docs/restaurant/handoffs/2026-10-30-ui-split-handoff.md for current implementation, failures, file map and next actions.
3. Read docs/restaurant/ui-split-scope-2026-10-30.md, requirements.md, architecture-and-tools.md, acceptance-tests.md and applicable CLAUDE.md conventions.
4. Resume the unfinished original-dashboard / touchscreen billing / screen separation / split-payment work. Original billing conversion is already present; do not rebuild a replacement frontend.

Latest evidence: restaurant Node tests 35 passed, JS lint and restaurant build passed; browser regression 6 passed and 7 failed. Current changes are not production accepted or packaged into a newly verified APK. Older green tests/APKs cover an earlier slice.

Workspace D:\vgl-restaurant-pos; branch codex/restaurant-offline. Significant local work remains untracked/uncommitted. Preserve it all. Keep tools/caches/temp on D:. No push, publication or private-reference uploads. Confirmed inclusive GST is unchanged. Native lifecycle/TVS/printer acceptance must be reported separately.

Read historical docs only as context: original-billing-conversion.md, quality-gate-2026-10-29.md and storage-migration.json. Previous root documents are retained under docs/restaurant/handoffs/2026-10-30-pre-ui-*.md. Their older statements do not override the current handoff.

Open a new chat in this same existing project, then paste NEW_CHAT_PROMPT.md. No new clone, worktree or project is required.
