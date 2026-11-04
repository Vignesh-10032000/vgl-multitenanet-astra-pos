# Restaurant POS project instructions

## Workspace and scope

- Work in `D:\vgl-restaurant-pos`. This is an independent clone of the user's POS.
- Do not modify the CRM at `C:\Users\L E N O V O\Documents\antigravity\busy-faraday` or the original POS at `D:\vgl pos`.
- Read `START_HERE.md`, `HANDOFF.md`, and `docs/restaurant/requirements.md` before implementation.
- The user requested preparation in the previous chat and development in a NEW chat. Preparation does not mean the restaurant conversion has already been implemented.
- Source repository: `https://github.com/Vignesh-10032000/vgl-multitenanet-astra-pos`.
- Baseline commit: `c6e39137ed0c84b431596a6d0d237d7b2ecdb66b`; working branch: `codex/restaurant-offline`.
- Preserve the billing screen's existing layout and checkout interaction. Add photo product tiles and remove stock-related behavior. Do not redesign the whole interface.
- Follow existing `CLAUDE.md` engineering conventions where applicable. The user's Android/offline/SQLite requirements supersede the old server-only deployment assumptions.

## Confirmed requirements

1. Installable Android APK, core operation completely offline on the TVS S6802, Android 11. OnePlus Android phone can be used for early testing.
2. No stock tracking, stock validation at checkout, inventory valuation, low-stock alerts, goods receipts, supplier/purchase workflows, or stock dashboards in this restaurant app. Bill quantities and item-sales reports still exist.
3. Products support manual add/edit, name, selling price, portion/variant, category, image, and active/inactive status. Images must be stored locally and remain usable offline.
4. Billing product cards are easy to tap and show the product photo, name, portion and price. Each menu portion has an independent price.
5. Customer form: name, phone, city only. The user's message called this the product screen, but its attached screenshot is the customer form; this interpretation is documented, not silently applied to product fields.
6. Sales: date range plus All / Cash / GPay (UPI) filters, with matching totals. Store UPI as the underlying payment type. A cashier marking a payment as GPay is not gateway-confirmed settlement.
7. Offline monthly auditor exports: CSV, XLSX, and PDF; invoice details, item detail, payment totals, daily/monthly summaries, and void/refund records. Exports must reconcile to the saved ledger.
8. Match the supplied 80 mm receipt style, with the restaurant's OWN identity and payment QR. The pictured vegetable-shop name, address, phone, barcode and QR are reference content, not restaurant data.
9. KOT/kitchen printing is explicitly excluded. Do not introduce it as a requirement.

## Data and printing rules

- Owner update 30 October 2026: recovery backups must be append-only documents in a user-selected shared folder, outside app-private storage and Android/data. Never automatically delete these backups. Normal uninstall must leave them in the shared folder. On reinstall, Android requires folder access again; discover and validate backups after reconnection, and authenticate the saved owner account before resuming. Keep old backup restore compatibility and never silently replace a nonempty ledger.
- Owner chose an offline username/password login on 30 October 2026. Use first-time owner setup with salted password verification, no preset credentials or mandatory cloud login. This is a local access lock, not a claim of database encryption.

- Owner correction on 2 November 2026: the restaurant menu/price card EXCLUDES GST. Add CGST 2.5% and SGST 2.5% on top of menu base prices for new bills (₹170 + ₹4.25 + ₹4.25 = ₹178.50 before configured rounding). Keep GSTIN `33BPFPD3960P2ZN`. This owner instruction supersedes the 28 October inclusive-price assumption only for future billing. Preserve every historical inclusive-GST receipt/payment snapshot and old backup compatibility; never recalculate saved bills. Keep the price basis configurable and snapshotted per sale.

- Use SQLite as the durable local source of truth; see `docs/restaurant/architecture-and-tools.md`. The old 500-sale queue and provisional invoices are not a substitute for independent offline billing.
- Use integer paise or exact decimal arithmetic. Preserve applicable existing money/tax tests. Never use binary floating-point for persisted monetary calculations.
- Save a sale, its item snapshots, payment, and final local bill number atomically before printing. A print failure must not lose the sale. Retry/reprint must not create another sale.
- Product edits/deactivation must not change historical sales. Retain void/refund audit records.
- Implement backup and tested restore; CSV/PDF/XLSX exports are not complete database backups. Do not copy an open SQLite file without a consistent backup/checkpoint strategy.
- The USB connection and field printing via ESC POS USB Print Service are already proven. Do not repeat discovery as a blocker. Custom APK printing and USB reconnect handling still need actual device tests.
- No root required. Do not root client hardware or assume an exact CPU/ABI based on `rk30board` or `S6802`.
- The GSTR-4 supports historical composition filing for FY 2025-26. Do not assume current FY 2026-27 tax status. Model receipt type configurably; confirm current status before live billing. Auditor exports do not constitute GST return filing.
- Missing final logo, actual product photographs, restaurant contact details, UPI payee and exact receipt font must be editable setup items, not reasons to halt initial development.

- Owner receipt alignment confirmation, 2 November 2026: GST rupee figures align directly beneath RATE. Keep summary labels on the left and historical/new accounting values unchanged. Counter optimizations must preserve draft durability, final atomic validation and all image/backup bytes; desktop results are not TVS acceptance.

## Tools and verification

- Owner requested product photos on 31 October 2026. Preserve the illustrative JPEG set and one-time image installation behavior in `docs/restaurant/menu-photos-2026-10-31.md`. Existing uploads, renamed products and explicit photo removals must retain priority; do not reset the `local:bundled-menu-photos-v1` marker to force images back. Complete backups include the image bytes. Menu base prices and historical bills remain unchanged by photo updates. New-bill GST follows the owner's 2 November exclusive-price correction above.
- Owner performance directive, 30 October 2026: optimize for the **TVS S6802**, using the collected hardware evidence in `docs/restaurant/tvs-performance-baseline.md`. The OnePlus 9R is a functional test device; its speed, RAM headroom and storage performance do not establish TVS readiness. Desktop/phone throttling is diagnostic only. Final performance acceptance requires measurements on the actual TVS with representative ledger/images/backups/exports, while preserving all live data.
- Project skills are in `.agents/skills`; they become discoverable when the new chat opens this project. Their generic defaults must not introduce unrelated iOS work, a different UI framework, mandatory cloud services or dependency-injection frameworks into this conversion.
- `.codex/config.toml` scopes documentation MCPs to this project. Load the project as trusted if the app requests it. MCPs are development tools, not runtime dependencies of the offline POS.
- Use Serena for targeted code navigation, Context7/Capacitor documentation for current APIs, and Playwright for billing-screen regression checks. Native/device tests are separate.
- Preserve the HTML/CSS/vanilla JS frontend and reuse business logic selectively. Flask/Jinja pages and server-dependent API calls cannot be made standalone merely by packaging the website URL.
- Read `docs/restaurant/acceptance-tests.md` before declaring a feature verified. Do not claim APK installation, offline restart recovery, USB printing or exact font matching from desktop tests alone.
- Do not publish, push, send messages or upload the local GST/reference files without explicit user instructions. Original source and private files are preserved locally.
