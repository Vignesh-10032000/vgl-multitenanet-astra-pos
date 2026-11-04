# Native receipt data-resource correction — 4 November 2026

Candidate **1.0.21 (22)** addresses the owner's photographed native asset error by allowing WebView to decode embedded `data:` resources while retaining the offline asset server and blocking other origins. See [the correction report](printer-asset-fix-2026-11-04.md). Verified: 22 Java tests, 4 receipt Node tests, 3 distinct browser scenarios (startup-wait correction/rerun recorded), JS lint/build, Android assemble/lint (0 errors / 20 warnings), signer and 68 bundled assets. APK hash-verified in Downloads. **Not installed or physically printed here.** No owner ledger or shared backup was accessed.

---

# RP 3230 routing correction — 4 November 2026

See [the correction report](printer-routing-2026-11-04.md). Candidate **1.0.20 (21)** makes USB printing primary, separates Android service/PDF printing, and adds the PDF-proven service setup. Owner photo confirms RP 3230 USB detection. Verified: 4 receipt Node tests, 3 browser scenarios, 19 Java unit tests, JS lint/build, Android assemble/lint (0 errors / 20 warnings). **Not installed; TVS/native raster/physical paper/reconnect acceptance pending.** No owner ledger or shared backup was accessed.

---

# Direct USB printing candidate — 4 November 2026

See [the scoped printing report](direct-usb-printing-2026-11-04.md). Adds direct ESC/POS USB output from the existing saved receipt; keeps Android print-service fallback. Focused checks: 4 receipt Node tests, 3 browser scenarios, 16 Java unit tests, JS lint/build and Android assemble/lint pass (0 errors / 20 warnings). **Not installed; native raster output, TVS/USB/physical-paper acceptance pending.** Billing/GST calculations, SQLite, analytics and backup/restore were not changed. No owner device/data was accessed.

---

# Regular / Parcel and fixed kilogram portions — 3 November 2026

Source/candidate **1.0.19 (20)** adds Regular / Parcel selection to Add/Edit Product, matching filters on Products/Billing, and optional fixed kilogram portions with independent prices changed through Edit. Historical bills, prices and images are preserved. See [the menu-options report](menu-options-2026-11-03.md) and its build record.

Verified: 103 Node checks, all 62 distinct browser scenarios (61 full-run passes plus corrected startup-wait GST rerun), JS lint/build, security scan (55 files / four rules / zero findings), Android build/lint (zero errors / 19 existing warnings), same signer as 1.0.18, and all 67 bundled web files. **Not installed or device-tested.** No owner device/ledger/credentials/shared backups were accessed. Last documented installed version remains 1.0.18; TVS/physical-print/native lifecycle acceptance is pending.

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

# Reliability audit — 31 October 2026

Latest detailed evidence: `TEST_PLAN.md` and `TEST_REPORT.md` at the project root; raw results under `test-results/reliability-audit/`. Final: **75 Node, 27 browser, 11 freshly rerun Java tests passed**. A reproduced invalid-discount checkout default was corrected without changing GST/prices/layout. Isolated 100/500/1,000-bill desktop stress and 50-bill actual OnePlus SQLite checks passed; live owner data/draft/backup metadata hashes remained unchanged.

Signed candidate `artifacts/restaurant-pos-1.0.9-audit-debug.apk` built with 45 matched assets, **not installed**. Android Lint retains 19 warnings; npm audit reports 13 moderate affected dependency nodes. TVS endurance, physical printing, actual reinstall/SAF recovery and new-candidate installation remain unverified. Previous version-specific evidence below is preserved.

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

Latest installed candidate: **1.0.6 (7)** at `artifacts/restaurant-pos-1.0.6-debug.apk`. Read `docs/restaurant/oneplus-device-2026-10-30.md` and `docs/restaurant/build-verification.json` first. OnePlus 9R / Android 14 checks covered owner login, native Cash/GPay/split bills, audited cancellations, offline process restart with saved bills and draft, shared-folder backup save/discovery and native CSV/XLSX/PDF saves. Device tests exposed and corrected a short-landscape sidebar navigation bug and a PDF picker `TransactionTooLargeException`; all 22 browser scenarios and 11 native unit tests pass, Android build/lint passes (0 errors, 19 warnings), and the scoped security scan reports zero findings. Existing 53 Node checks cover unchanged business logic.

The physical phone now contains the owner's saved bill `AR/2627/000001` for ₹870 and three cancelled device-test bills (`000002`–`000004`, customer `DEVICE TEST - NO REAL PAYMENT`). Preserve these records, credentials and the user-selected shared `PC` backup folder. No app data was cleared or uninstalled. Native testing used no default internet network. Physical printing, TVS S6802 acceptance, process death while a picker is open and actual uninstall/reinstall restore remain unverified. Earlier statuses below are historical; preserve confirmed inclusive GST and all local work.

---

# Current workspace upgrade — 30 October 2026

Read [the current implementation and evidence](workspace-upgrade-2026-10-30.md) and [APK build record](build-verification.json). The 1.0.4 (5) candidate includes refreshed Sales/Reports, weekly/monthly cards, product form/SVGs, offline username/password login and shared-folder backups. 53 Node tests, 21 browser scenarios and 5 Java tests passed; JS lint/build passed and Android Lint reports 0 errors/19 warnings. Native uninstall/reinstall, provider and physical printer acceptance remain pending. Prior records below apply to their stated older builds.

---

# Current verification — 30 October 2026

The UI, original dashboard, separate Sales/Reports and split-payment continuation now has 19 passing browser scenarios, 48 passing unit/frontend checks, clean JavaScript lint and a passing restaurant build. See [the current detailed evidence and file list](verification-2026-10-30-ui-split.md) and [the latest APK build record](build-verification.json). Device/native offline lifecycle, SAF/provider behavior and physical printer acceptance remain unverified.

All older results below are retained as history and apply to their stated builds.

---

# Fresh verification — 29 October 2026

The **original** billing template/controller now power the active build. See [conversion map](original-billing-conversion.md) and [quality gate](quality-gate-2026-10-29.md). Fresh results: **40 Node checks**, **13 Playwright scenarios**, **4 Java writer tests** passed; JavaScript lint passed; Android Lint has **0 errors, 19 warnings**; the limited local Semgrep rules reported **0 findings across 23 files**. Inclusive GST, immutable snapshots, atomic saves/rollback, duplicate protection and final numbering remain covered.

The versioned **1.0.2 (3)** debug APK is `artifacts/restaurant-pos-1.0.2-debug.apk`. Its signature and all 25 built web assets were verified; Capacitor adds its two generated Cordova bridge files. `build-verification.json` records size/hash and preserves the previous build record. The old `artifacts/restaurant-pos-debug.apk` is retained.

POS Android SDK/user data and Playwright browsers moved to D: with SHA-256 checks and verified compatibility junctions. See `storage-migration.json`; project commands now preload D: temp/browser/cache paths. The post-move browser suite passed all 13 scenarios, and the restaurant ledger suite passed all 29 checks.

**NOT VERIFIED:** Android install/native SQLite process-death or reboot recovery, native provider/restore/export behavior, TVS performance and actual APK print/reconnect/paper-out. No device or emulator is connected. Follow [device acceptance](device-acceptance.md). Desktop CDP measurements are diagnostic only.

The remainder is the preserved earlier verification history:

---

# Verification

## GST follow-up — owner confirmed 28 October 2026

The owner explicitly confirmed current live CGST **2.5%** and SGST **2.5%**, **included** in the existing menu prices. GSTIN `33BPFPD3960P2ZN` was read locally from the supplied GST document. Current defaults now use tax-invoice mode; the original untouched blank/training tax configuration upgrades once. Stored historical receipts, menu/customer edits and configured alternative tax settings are preserved.

- `npm test`: **36 passed**, 0 failures (11 preserved frontend + 25 restaurant, including five new GST checks).
- `npm run build`: PASS.
- `npm run test:restaurant:browser`: **7 passed**, 0 failures, including GSTIN in saved/reprinted receipt, cart tax split, unchanged total, and retained layout geometry.
- ₹170 example: taxable **₹161.90**, CGST 2.5% **₹4.05**, SGST 2.5% **₹4.05**, included GST **₹8.10**, final total **₹170.00**. ₹200 tendered still yields ₹30 change.
- Auditor invoice register now also carries the saved GSTIN, taxable amount, both component rates and amounts. Real XLSX parsing verifies numeric tax cells and unchanged total.
- APK rebuilt as **1.0.1 (versionCode 2)** and signature verified. Latest hash, size and asset-byte verification are in `build-verification.json`; APK is `artifacts/restaurant-pos-debug.apk`. Physical device/USB printing tests remain pending.
- Preview: `http://127.0.0.1:5174/`. The raw `file:///.../restaurant/index.html` path is source, not the running frontend. Verified localhost shows Tax invoice, CGST 2.5%, SGST 2.5%.
- Receipt screenshot: `artifacts/gst-receipt.png`. Earlier training-default and APK-hash statements below describe the initial build, before this owner confirmation.

## Initial implementation checks — 28 October 2026

The restaurant app has now been implemented and a debug APK produced. The preparation results below remain historical evidence. Implementation details and setup are in `development.md`; exact APK hash/size/ABIs are in `build-verification.json`.

| Check | Actual result |
| --- | --- |
| `npm test` | PASS: **31** checks (11 preserved frontend + 20 restaurant), 0 failures; preserved tax parity covers 200 shared scenarios |
| `npm run build` | PASS: standalone bundled restaurant HTML/CSS/JS, all four local fonts and local logo/menu asset |
| `npm run test:restaurant:browser` | PASS: **6** Playwright scenarios, 0 failures |
| Billing layout regression | 1920 × 1080 menu/cart/workspace bounds exactly equal source template/CSS baseline; screenshot in `billing-desktop.png` |
| Core calculation | ₹170 bill, ₹200 tendered, ₹30 change; independent ₹450/₹230 parcel portions; discounts/included-tax/negative rounding checked |
| SQLite durability/atomicity | Reopened a disposable real SQLite file; injected payment failure rolled back sale/lines/payment/number/draft deletion; concurrent retries produced one bill |
| Independent bill capacity | 510 saved bills in isolated SQLite; no sync or 500-bill stop |
| History and corrections | Product/customer edits retain sale snapshots; void/refund records linked; zero-total void remains marked; annual/Kolkata day/month boundaries checked |
| Browser persistence | Local photo, Tamil customer and unsaved cart survive reload; backup restored real JPEG/price/draft into a separate clean browser context |
| Cash/GPay | Matching filtered totals, `upi` stored; no external requests in billing scenario; checkout also exercised with browser networking disabled after local load |
| CSV/XLSX | CSV reopened with Python `csv`; XLSX reopened with ExcelJS; numeric amount cells, quoting/newlines/Tamil/formula protection, correction and summary values checked |
| Monthly PDF | 35 bills, discounts/negative rounding and previous-month refund reconcile to ₹5,910; pypdf parsed 23 pages, Poppler rendered pages for visual inspection; repeated headers and Tamil visible |
| Complete backup/restore | Node and browser disposable restores passed, including settings, images, numbering and audit/drafts. Truncated, modified, missing-image and inconsistent-payment backups rejected without replacing active ledger |
| Android compile + lint | PASS: `scripts/build-restaurant-android.ps1 -SkipWebBuild -Lint` after latest web build; 0 lint errors, 19 warnings |
| APK signature | PASS: build-tools 36.1.0 `apksigner verify --verbose`, v2 signature, one signer |
| Packaged source freshness | All **24** web asset files inside the final APK exactly match the latest `dist/restaurant` bytes |
| APK artifact | `artifacts/restaurant-pos-debug.apk`, **14,513,272 bytes**; SHA-256 `d3224f42868fa6c6acc3c80bb9ffeb661861b7a80385234ea244af2526188f93` |
| Native ABIs packaged | arm64-v8a, armeabi-v7a, x86, x86_64; terminal ABI remains unrecorded, not guessed |
| Dependency audit | `npm audit --json`: **0 vulnerabilities**; report in `implementation-npm-audit.json` |
| Original resources | All 12 local copied references retain manifest SHA-256 values |
| Scope | Original POS and CRM application sources untouched; no publish/push/message/reference upload |

The 19 Android lint warnings concern newer tool/dependency versions, Android 16 orientation behavior, Android 12 extraction-rule guidance, and unused/default generated icon/splash resources. There are no lint errors; lint completion does not validate hardware behavior. Vite reports the lazily loaded ExcelJS chunk exceeds its generic 500 KB warning threshold; it is loaded only when XLSX export is selected. The normal restaurant main JS is about 64 KB before gzip. Legacy builds retain their old Flask font-path warnings; the restaurant bundle includes the corresponding local font files.

The initial Gradle build failed on this Windows environment's AF_UNIX temporary socket path. A project-local short native temporary directory fixed it; both compile and lint then passed. The workaround is recorded in the build script, not a device requirement.

**Not yet verified:** APK installation on OnePlus/TVS; actual Android native SQLite process-death/reboot recovery; airplane-mode restart/export; Android document-provider permissions/errors; native backup/restore in a disposable installation; custom APK → ESC POS USB Print Service output; USB disconnect/reconnect, power/paper-out/reboot; exact printable width/font/physical logo/QR readability. No device was attached and no emulator system image was installed. The earlier field-tested USB connection remains established evidence. This APK starts in training mode; current tax/UPI setup needs owner/accountant confirmation before live use.

Desktop artifacts are in `artifacts/` (APK, billing/phone screenshots, sample CSV/XLSX and monthly PDF) and detailed test output in `test-results/restaurant-artifacts/`. The PDF is deliberately rasterized for Tamil shaping; use CSV/XLSX for machine-readable auditor data.

## Preparation verification (historical)

Checked 28 October 2026, Asia/Kolkata. This report covers project preparation and the existing web baseline, not the future restaurant APK.

| Check | Observed result |
| --- | --- |
| Original local HEAD vs linked GitHub repository HEAD | MATCH: `c6e39137ed0c84b431596a6d0d237d7b2ecdb66b` |
| Independent clone HEAD | Same commit; branch `codex/restaurant-offline` created |
| Original local tracked source | `git diff --name-only HEAD --` empty |
| New clone tracked application source | `git diff --name-only HEAD --` empty after preparation/build |
| Original references | 12 copied, no missing files, all copied SHA-256 values match originals |
| Menu preparation | 36 unique entries, positive integer-paise prices, independent 450.00/230.00 mutton parcel prices checked |
| Project skills | Five SKILL.md files present; source and hashes recorded in tooling-inventory.json |
| Project MCP configuration | TOML parsed; restaurant_context7 and capacitor entries present |
| Context7 direct MCP endpoint | initialize and tools/list passed |
| Capacitor direct MCP endpoint | initialize, tools/list and v8 Android search_docs passed |
| Codex current CLI tool listing | Existing global entries only; new project entries were not loaded in that command's trust context |
| SDK/ADB | SDK present; absolute-path ADB version command passed |
| Node/npm | Node 24.12.0; npm 11.6.2 |
| `npm ci --ignore-scripts` | PASS; 24 packages added, lockfile preserved |
| `npm run build` | PASS; Vite 7.3.6 emitted production assets |
| `npm test` | PASS: 11 tests, 0 failures, including 200 shared tax fixtures and asset-budget check |
| `npm audit --json` | REPORTED: one high-severity vulnerable package, Vite; see below |
| Backend/integration/browser tests | Not run in preparation; no application behavior was modified |
| Android APK build/install | Not run; Android app conversion has not been implemented and Java was not on PATH |
| OnePlus/TVS/printer tests | Not run in preparation; field report remains the earlier hardware evidence |

## Build portability observations

The baseline build warned that four `/static/fonts/...woff2` URLs remain to be resolved at runtime. Their source files are present in `src/vglpos/web/static/fonts`, but the current Flask-served paths must be deliberately rebased/bundled for a fully local Android app. A successful web asset build does not establish standalone APK operation.

The passing outbox test validates the OLD 500-bill limit. It is baseline evidence, not a desired acceptance condition for the standalone restaurant ledger. Update that behavior and its tests together during conversion.

## Existing dependency advisory

`npm audit` reported Vite 7.3.6 within the affected `7.0.0 - 7.3.6` range and an available fix. The report contains launch-editor Windows argument/command handling advisories and development-server cross-origin/path-access advisories. This is an inherited development-tool dependency finding; do not describe it as a proven exploit of restaurant sales data or the future APK.

Raw report: `docs/restaurant/baseline-npm-audit.json`.

The baseline lockfile was intentionally retained while comparing source. In the implementation chat, review a supported patched Vite version and apply the smallest compatible dependency update, then rerun build, asset budgets and frontend tests. Do not run an unreviewed broad `npm audit fix --force`.

## New chat/configuration boundary

Endpoint checks used direct MCP protocol calls from a temporary preflight process. They demonstrate server reachability and responses, not registration in the current chat's callable tool inventory. Open `D:\vgl-restaurant-pos` as a primary trusted local project so `.codex/config.toml` and `.agents/skills` can be discovered by the next chat. Verify the tool inventory there.

There was no available `create_thread` tool in this chat. The project handoff and `NEW_CHAT_PROMPT.md` provide the manual continuation path. No sidebar thread has been created automatically.


## 3 November 2026 — OnePlus 1.0.17 update

In-place installation, installed APK hash, actual sign-in screen, native schema-v3 migration, database integrity/foreign keys, original ledger/product/draft columns and image/account preference retention verified on OnePlus OPD2305 / Android 14. Details and limits: [Pad Go installation](padgo-install-2026-11-03.md). No native test sale or physical printing; TVS acceptance remains pending.
