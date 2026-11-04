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

# Current implementation — 30 October 2026

The original billing and original dashboard now power the local restaurant app. Dashboard/Sales/Reports are separate, with independent defaults and Reports-only exports. SQLite schema v2 supports atomic Cash + GPay payments and explicit returned channels; v1 databases/backups migrate. Item/invoice exports include selected-payment shares. Read [the current implementation and verification map](verification-2026-10-30-ui-split.md) for files, checks and remaining hardware acceptance. The APK candidate is version 1.0.3 (4); see build-verification.json for its final status/hash.

The implementation history below is preserved. References to eight worksheets or version 1.0.1/1.0.2 describe earlier slices; current XLSX has nine worksheets.

---

# Restaurant implementation — 28 October 2026

**Latest GST update:** the owner confirmed current regular GST billing at CGST 2.5% + SGST 2.5%, **included** in existing menu prices, using GSTIN `33BPFPD3960P2ZN` from the supplied document. Defaults now open in tax-invoice mode. Original blank/training tax settings upgrade once; unrelated store edits and historical receipts are retained. A ₹170 sale prints taxable ₹161.90, CGST ₹4.05, SGST ₹4.05 and total ₹170.00. The invoice export carries the saved GSTIN, taxable amount, component rates and amounts. New APK version is **1.0.1 (2)**. References below to the initial training default describe the first build before this owner confirmation.

The standalone application is in `restaurant/`; Android packaging and the local print/save bridge are in `android/`. Work remains on `codex/restaurant-offline` in this independent clone. No push, publication, message, or reference upload was performed.

## Run and build

```powershell
npm ci
npm run dev
npm run build
npm test
npm run test:restaurant:browser
npm run android:build
```

The browser preview is at `http://127.0.0.1:5174`. `npm run build` now builds the restaurant app, with no landing or tenant screen. `build:legacy` and `dev:legacy` retain access to the original Flask asset workflow for regression tests. `npm test` builds those legacy assets, runs the existing 11 frontend checks (including all 200 shared tax fixtures), and the new restaurant ledger tests.

`scripts/build-restaurant-android.ps1` uses JDK 21 from `JAVA_HOME`, or the checksum-verified project-local `.tools/jdk` installation made during this work. It uses the existing Android SDK. Gradle caches and the Windows JVM socket temporary directory stay in `.tools/`. A short native temporary path resolved the observed Windows `UnixDomainSockets.connect0` / loopback failure. The script accepts `-SkipWebBuild` and `-Lint`; use the former only after building the latest web assets.

The APK is a debug build for device acceptance. Its application ID is `in.vgl.restaurant`, minimum API 24, target/compile API 36. It uses user landscape orientation and keeps the screen on at the counter. No ABI was inferred from the terminal name. The packaged native libraries support multiple ABIs.

## What is implemented

- The original main/pos styles and two-panel billing structure are reused. Automated panel geometry equals the source baseline at 1920 × 1080. Menu tiles add a local photo, name, portion and independent price; neutral local dish symbols appear until photographs are selected. Search, quantity controls, discount, walk-in/customer, Cash/GPay, quick cash, change and saved receipt preview are available.
- The APK opens straight into billing. No landing, tenant selection, server account, inventory, suppliers, purchases, stock decrement, outbox capacity limit, provisional number, or KOT appears in this build. The Flask source is retained only as reference/regression material and is outside the bundled runtime.
- `@capacitor-community/sqlite` 8.1.1 supplies native SQLite. The SQL schema has products, customers, sales, immutable line/customer/store snapshots, payments, financial-year sequences, adjustments, print attempts and drafts. Writes use a serialized repository and explicit transaction. Sale, items, payment, final number and draft removal commit together. A unique operation ID rejects duplicate/retried submissions without allocating another number.
- All persisted money uses integer paise; multiplication/division that could lose precision uses BigInt. Cash tender/change are separate from revenue. Dates are UTC instants and report boundaries are Asia/Kolkata midnight through the next exclusive midnight. Bill numbers use `AR/2627/000001` style, a configurable 1–4 character prefix, and a six-digit annual counter, at most 16 characters. Exhaustion is rejected transactionally, never wrapped. The CBIC numbering rule is recorded below; this implementation is not a tax-filing certification.
- Initial menu data comes from `resources/menu-transcription.json`. In particular mutton parcel 1 kg is ₹450 and half kg is ₹230. Product edits, images and active status are local. Saved sales retain original prices/names/portions and customer/store data.
- Customer entry is name, phone and city. Walk-in checkout requires no customer record.
- Sales/report/dashboard use one date/payment query. Filters are All, Cash and GPay; the stored payment method is `upi`. No gateway verification is performed. Displayed summaries, item sales, daily/monthly exports and correction records derive from the saved ledger.
- Voids and refunds append reason/date/amount records linked to the original bill. Numbers are retained. Correction cash/UPI totals use the correction's recorded date, including corrections to bills from earlier periods. Item quantities describe originally invoiced dishes; the separate correction register carries monetary returns. The operator must perform the actual return of funds.
- CSV includes named sections for invoices, items, summary, daily/monthly totals, item sales, corrections and print attempts. It is UTF-8/BOM, quoted and protects formula-leading text. Exact numeric decimal amounts, including negative rounding, remain numeric CSV fields.
- XLSX provides the same eight worksheets with frozen headings, filters, column widths and amount formats. Exact decimal strings are written directly into numeric worksheet XML; money calculations never pass through binary fractions. Customer/product text is kept as protected text. ExcelJS and JSZip load on demand.
- PDF is generated completely offline. Raster pages use the browser's shaping of bundled Inter/Noto Sans Tamil, avoiding broken Tamil glyph shaping in a PDF text engine. Wider registers use labelled field blocks and repeat the dataset/period/page header. This PDF is image-based, so use CSV/XLSX for machine import or searchable data. A 35-bill/month-boundary case produced 23 readable pages.
- Images are resized JPEGs in app-managed `Directory.Data`, referenced by content-addressed relative filenames. They are immutable: changing a logo cannot rewrite an old bill. Complete logical backups read all tables inside one SQLite transaction, then include referenced files and a SHA-256 envelope. Restore checks schema/version, columns, constraints, foreign keys, bill/line/payment reconciliation, numbering, corrections and image checksums in a disposable SQLite WASM database. Files stage before one active-database replacement transaction. No live SQLite file is copied. An older backup replaces the ledger/counter: the restore dialog explicitly warns against reusing an older counter for live bills.
- Android save/export uses the system Create Document picker and only reports saved after the provider write succeeds. Print/reprint uses the existing Android WebView print adapter and native PrintManager, selected 80 mm media, 203 DPI and no margins, allowing the proven ESC POS USB Print Service to be selected. Print attempts are separate from sales. “Submitted” is not physical-paper confirmation.

## Store details and setup

The supplied Google search URL was attempted but was not readable by the web tool. Public listings were reviewed instead:

- [Zomato store listing](https://www.zomato.com/pollachi/arafa-restaurant-pollachi-locality): Arafa Restaurant, 10 Kamarajar Street, Mahalingapuram, Pollachi.
- [Yappe listing](https://yappe.in/tamil-nadu/mahalingapuram/arafah-briyani-restaurant/1980046): Arafah Briyani Restaurant, Mahalingapuram, Tamil Nadu 642002.

The editable seed uses **Arafah Briyani Restaurant**, **10, Kamarajar Street, Mahalingapuram, Pollachi, Tamil Nadu 642002**. No public logo was conclusively identified. The app instead displays the actual Tamil logo area of the owner's supplied menu photograph using a CSS image viewport; no new logo artwork was invented. The original photo remains unchanged and is bundled locally. A separate uploaded logo takes precedence and is covered by backup. Public phone listings were not automatically adopted because the user requested name/address.

Initial receipt mode is **Training — not for live billing**. Current GSTIN and accountant-confirmed receipt/tax mode must be entered before selecting Bill of Supply or regular tax invoice. No current FY status was inferred from historical GSTR-4. The optional regular-tax path uses a configured included GST rate for local counter sales. Merchant UPI/payee must be entered and explicitly confirmed before a payment QR appears. No QR from the reference shop is reused. Receipt typeface, footer, phone/address/logo are editable.

Current numbering reference: [CBIC Rule 46](https://taxinformation.cbic.gov.in/content-page/explore-rules/1000136/1000001) specifies an annual unique consecutive serial number of at most sixteen characters. Actual tax eligibility and filing remain with the accountant.

## Verification boundaries

See `verification.md` for commands and counts. The browser adapter runs real SQLite WASM, persisted as an IndexedDB database image for desktop preview only. Browser persistence is not the Android durable storage implementation. A browser reload test, a Node SQLite file reopen, and an APK compile are separate evidence from Android process-death/device-reboot recovery.

No Android device or installed emulator image was available. Next acceptance work is to install the APK on OnePlus/TVS, confirm WebView and local setup, force-stop/reboot offline, test images/exports/backup restore in a disposable install, and print/reprint via ESC POS USB Print Service with disconnect/paper-out/reboot cases. The physical USB link is already proven; do not repeat discovery as a prerequisite. Match printable width, Tamil, logo/QR and exact font on actual paper. Final menu photographs, high-resolution logo, phone, UPI and current tax setup remain editable owner inputs.
