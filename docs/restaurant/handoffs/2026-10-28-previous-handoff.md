# Conversation handoff: offline restaurant POS

## Implementation update — 28 October 2026

GST follow-up: the owner has now explicitly confirmed **CGST 2.5% + SGST 2.5%, included in menu prices**, for current live billing. GSTIN read locally from the supplied document is `33BPFPD3960P2ZN`. New installation defaults are regular tax invoice, total GST 5%, owner-confirmed. The original blank/training tax settings upgrade once without rewriting saved bills or other store settings. Receipt and billing show taxable value and separate labelled tax amounts; the auditor invoice register includes snapshot GSTIN and split tax values. Older statements below about pending current tax confirmation describe the earlier preparation state.

The first implementation now exists in `restaurant/` and `android/`. It opens directly into the preserved billing layout. There is no landing page, tenant chooser, server login, stock workflow, or remote sync dependency in the Android bundle. The old Flask source remains available as reference; it is not packaged as the restaurant runtime.

Implemented: native SQLite adapter, local browser preview, exact-paise atomic checkout/final numbers, 36 editable menu portions, local photo editing, three-field customers, Cash/GPay filters, immutable receipts/reprints, correction audit, offline CSV/XLSX/PDF, and validated complete logical backup/restore. Settings seed the public store name/address and reuse the actual Tamil logo area of the supplied menu; replacement branding, contact and UPI are editable. Training mode is the initial receipt mode.

Current instructions and verification: `docs/restaurant/development.md` and the implementation section in `docs/restaurant/verification.md`. APK compilation and desktop tests do not establish device/USB behavior. No device was attached; TVS/OnePlus installation, native SQLite lifecycle/restore and actual printing still require tests. Nothing was pushed or published, and the original POS/CRM were untouched.

The sections below retain the original preparation context; statements that implementation had not started describe that earlier state.

## User's intent and authorization

The user first requested analysis of a field report, then clarified that document recommendations were not instructions to execute. Later they requested an offline installable restaurant POS based on existing VGL software, with work isolated from their CRM. They explicitly chose `D:\vgl-restaurant-pos`.

Latest request: record the simplified restaurant features, verify that the local source is pushed to the linked GitHub repository, research/install suitable development skills and MCPs, gather all supplied resources into this folder, and continue implementation in a NEW chat under this project.

The user dislikes repeated confirmation requests and unnecessary hardware-discovery blockers. Proceed on confirmed requirements and make routine engineering decisions. Ask only for genuine business ambiguities that affect irreversible outcomes. Final branding/contact/UPI/font assets can remain configurable during initial implementation.

## Source verification

- Original local POS: `D:\vgl pos`.
- Linked repository: `https://github.com/Vignesh-10032000/vgl-multitenanet-astra-pos`.
- Its remote name in the original local checkout is `astra`; the original `origin` points to a different repository, `VGL--POINT-OF-SALE`.
- Original local HEAD and linked repository's advertised HEAD both equaled `c6e39137ed0c84b431596a6d0d237d7b2ecdb66b` during this preparation.
- Original local branch was `codex/landing-upgrade-published`; linked default branch is `main`.
- Original local tracked files had no changes. Untracked local items existed: `.antigravity/`, `.serena/`, `run_localhost.bat`, and `scripts/run_local.py`. These untracked extras were not presumed pushed or copied into the new source baseline.
- The linked repository was cloned independently into this folder. Branch `codex/restaurant-offline` was created here. Original CRM and original POS application source were not edited.

See `docs/restaurant/source-verification.json` for checked values.

## What the existing application contains

Python 3.12 / Flask / SQLAlchemy / PostgreSQL / Redis / Celery server; Jinja templates and Vite/vanilla JavaScript frontend; Inter and Noto Sans Tamil assets; billing/cart/payment logic; products; customers; shifts; receipts; reports; offline IndexedDB cache and signed synchronization queue.

Important source anchors:

- `src/vglpos/web/templates/pos.html`, `src/vglpos/web/static/src/js/pos.js`: preserve checkout layout; remove stock displays and stock checks; introduce image product tiles.
- `src/vglpos/web/templates/products.html`, `src/vglpos/web/static/src/js/products.js`: manual product editing exists but exposes retail stock fields; photo handling must be added/confirmed.
- `src/vglpos/web/templates/customers.html`, `src/vglpos/web/static/src/js/customers.js`: name/phone/city exist among excessive fields.
- `src/vglpos/web/templates/sales.html`, `src/vglpos/web/static/src/js/sales.js`: server-backed sales listing and filters.
- `src/vglpos/web/static/src/js/offline-db.js`: IndexedDB cache and 500-entry outbox limit.
- `src/vglpos/web/static/src/js/offline.js`: server bootstrap and sync required; provisional numbering.
- `src/vglpos/web/templates/offline_receipt.html`: provisional offline invoice, finalized after sync.
- `src/vglpos/web/static/src/js/receipt.js`: browser `window.print()` path, not a native USB implementation.
- `src/vglpos/web/static/src/js/tax-engine.js`, `payment-display.js`, `data.js`: reusable exact-arithmetic logic and tests.
- `src/vglpos/web/static/src/sw.js`: existing PWA service worker; assess/disable its registration in the native bundled-asset build to avoid interference.
- `vite.config.js`: builds JS entry points with `/static/dist/` base. This is not yet a static HTML app shell for Capacitor; Jinja and URL routing need explicit adaptation.

## Confirmed hardware and printing

- TVS Electronics S6802 Android terminal, Android 11, approximately 4 GB RAM, 128 GB storage, 1920 x 1080 landscape touchscreen, Wi-Fi.
- Rockchip platform / `rk30board`; exact CPU model and Android supported ABIs were not shown in GENERAL/SCREEN photos. This is not an identified CPU fault and must not block planning.
- App-estimated 6.88-inch screen diagonal and two logical display entries are not physical screen measurements or proof of a second panel.
- External TVS RP 3230 thermal printer, USB connected by the user. Connection and actual print output are resolved facts.
- Field test used ESC POS USB Print Service by Looped Labs, `com.loopedlabs.usbprintservice`, at 80 mm / 203 DPI.
- Browser sample bill and text/image test printed on paper. Cutter disabled; drawer unused. Reconnect/stress/reboot behavior and new custom APK printing remain unverified.
- Initial testing may use a OnePlus Android phone. Confirm supported Android version and test TVS printing separately. Phone USB printing additionally needs USB host/OTG support and a suitable connection.
- Do not root the TVS or request unnecessary low-level access.

## Latest product scope

- Keep the existing billing screen arrangement and interaction.
- Remove stock and inventory features completely from this restaurant workflow, including checkout restrictions and dashboard/report stock metrics.
- Add product pictures for tap-to-bill; manual add/edit product with independent variant prices and locally saved images.
- Simplify CUSTOMER screen to name, phone and city. This interprets a wording mix-up using the attached customer screenshot.
- Sales payment filters: All, Cash, GPay/UPI plus date range and totals.
- Month-end auditor exports in CSV, XLSX and PDF from saved sales, with consistent totals and audit information.
- Receipt should closely follow the supplied reference's hierarchy, typography, columns and large total. Exact font file/name is unknown; physical sample comparison is needed for acceptance.
- No KOT/kitchen printer.

Detailed acceptance is in `docs/restaurant/requirements.md` and `acceptance-tests.md`.

## Restaurant and tax evidence

Historical GST return identifies ARAFA RESTAURANT, GSTIN `33BPFPD3960P2ZN`, legal name ABUTHAHIR DASTHAHIR, FY 2025-26. It is historical composition-scheme evidence, not a live taxpayer-status check for FY 2026-27. Do not copy the demo retail tax invoice indiscriminately. Current tax mode/receipt wording requires confirmation before live deployment.

The vegetable-shop receipt is a STYLE reference. Its shop name, contact, address and UPI QR must not become the restaurant's data. The menu photo is the restaurant price source. There are 36 photographed menu entries/portions in the transcription. Mutton biryani parcel 1 kg is 450.00 and 1/2 kg is 230.00, so deriving all prices proportionally would be wrong.

No actual separate product-photo files, final restaurant logo file, verified current address/phone, final restaurant UPI payee, or exact receipt-font source have been supplied. Support editable configuration/upload instead of inventing these values.

## Preparation completed and remaining work

Prepared: isolated source clone/branch, references and checksums, menu transcription, requirements, architecture research, installed project-local skills, scoped documentation MCP configuration and connection checks.

Not implemented: stock removal, product photos, simplified forms, local SQLite ledger, Android packaging, exports, native printing, device acceptance. Do not report these as complete merely because preparation files exist.

Development starts in the new project chat using `NEW_CHAT_PROMPT.md`.
