# Restaurant requirements

Status: user-confirmed scope captured 28 October 2026; first implementation and desktop checks completed. Native installation, lifecycle, and printer acceptance remain pending. See `development.md` and `verification.md`.

## Product goal

A simple, fast, installable Android restaurant billing app that completes normal daily operation without internet or an external computer/server. Reuse the existing VGL billing interface and suitable logic. This is one restaurant/terminal initially; cloud multi-tenant features are not required for the cashier workflow.

## Screens

| Area | Required behavior |
| --- | --- |
| Billing | Keep current arrangement, cart and checkout flow. Show tappable image/name/portion/price cards. Cart quantity controls, exact totals, Cash/GPay selection and receipt/reprint remain. |
| Products | Manual add/edit, item name, category, independent portion/variant price, image upload/replace and active/inactive switch. Supply the menu transcription as editable starter data. No stock fields, quantity-on-hand, reorder values, batch, expiry, supplier, mandatory SKU or barcode setup. |
| Customers | Name, phone and city only. Name/phone search. Walk-in checkout without creating a customer remains possible. Phone/city should not block a walk-in bill. |
| Sales | From/to dates and payment filter All / Cash / GPay (UPI). Saved bill list, bill detail, reprint, totals and export use the same filter set. |
| Dashboard | Sales, bill count, cash/UPI totals and useful daily/monthly trends. Remove low-stock, stock value and other inventory metrics. |
| Reports | Sales register, payment split, item sales, daily/monthly summary and auditor export. No stock valuation or purchase/inventory reports. |
| Settings | Restaurant identity/contact, GST/tax mode, receipt branding/font configuration, printer, local data backup/restore and simple staff access as needed. |

## Remove stock behavior across layers

Hiding a column is insufficient. Remove stock badges, out-of-stock disabling, insufficient-stock rejection, stock deduction on sale, low-stock thresholds, stock/cache adjustment dependencies, held-bill stock messages, inventory valuation widgets and inventory/purchase navigation from this restaurant build.

Do not confuse sales quantities with inventory. Quantity 2 of a dish still needs calculation, printing and item-sales aggregation. Dish availability can be managed with active/inactive status; it does not need ingredient or stock tracking.

## Images and menu data

Owner update, **3 November 2026**: Add/Edit Product includes a Regular / Parcel menu type. Products and Billing provide All / Regular / Parcel filters; an assigned item appears only in its matching type (and All), combined with existing category/search. Add an optional kilogram quantity for a **fixed portion**, with its own owner-entered selling price. The price stays fixed until edited; do not derive a half-kilogram price from another portion or introduce arbitrary weighed checkout.

- Store selected image files inside app-managed storage and persist their relative identifiers in the database.
- Images must survive airplane mode, app restart and backup/restore. Resize to appropriate thumbnails to keep tap-to-bill fast.
- No remote image URL dependency during billing. Use a neutral local placeholder until real dish pictures are provided.
- Seed data is transcribed from the supplied menu; review before live use. Preserve independent prices for full/half/quarter and 1 kg/1/2 kg portions.
- Keep raw source labels in the transcription. Spelling corrections may be presentation choices, not undisclosed changes to the source evidence.

## Payment behavior

Required payment choices are Cash and GPay (UPI). GPay is a visible label for a UPI payment recorded by the cashier. No automatic GPay/UPI payment verification, bank settlement feed or payment-gateway account has been authorized or supplied. Do not imply a printed QR confirms payment.

Keep payment amounts separate from amount tendered and change. For the current ₹170 base-price example, the bill is ₹178.50 including added GST; ₹200 tendered gives ₹21.50 change. Collected bill revenue is ₹178.50, with taxable sales and GST reported separately. Historical inclusive ₹170 bills retain ₹30 change from ₹200 tendered. Avoid hiding mixed legacy tenders if existing data is ever imported; define migration separately. Split payments, credit, loyalty and gateway integrations are not added scope by default.

## Offline ledger and audit integrity

- Core menu, product/customer editing, checkout, bill numbering, sales search, reports, export and reprint work without external APIs.
- Commit the sale, line snapshots, totals, payment and final device-generated bill number in one database transaction.
- Guard duplicate submissions with a unique operation identifier. Printing/reprinting is a separate operation referencing the saved sale.
- Final invoice numbering must be unique and appropriate to the configured financial-year series. Store voided bill numbers and their audit history.
- Keep immutable sale item name/portion/price snapshots even after menu edits or product deactivation.
- Corrections/refunds/voids preserve references, timestamps, amounts and a reason; do not silently delete history.
- Store business timestamps consistently and derive report periods in Asia/Kolkata. Specify inclusive date ranges through an exclusive next-day boundary internally.
- A failed print leaves a saved sale retrievable for retry, without increasing sales totals again.
- There is no mandatory 500-pending-bill stop or later server-finalization dependency in the standalone workflow.

## Auditor exports

Provide CSV, XLSX and PDF formats, fully generated offline. The auditor's exact import template can be added later if supplied; do not claim compatibility with a specific accounting package without a test.

Export datasets:

1. Invoice register: number, date/time, customer when present, line count, subtotal, discount, round-off, final total, receipt/tax mode, payment type and status.
2. Item detail: bill number/date, item/portion snapshot, quantity, unit price and line total, plus any applicable configured tax/discount columns.
3. Summary: period, gross/net sales, bill count, Cash and GPay totals, discounts, round-off, void/refund totals and daily totals.
4. Audit exceptions: voided/refunded bills and original bill links; reprints should be distinguishable from new sales if logged.

The on-screen filter, file contents and summary totals must agree. For XLSX, preserve exact decimal values and sensible number formats; escape formula-leading customer/product text. CSV uses UTF-8 (optionally BOM for Excel) with correct quoting and formula-injection handling. PDF needs readable headers, pagination, repeated table headings and Tamil rendering when used.

Month-end exports help the auditor; they are neither GST portal filing nor a certification that a tax return is correct. Report observed data and leave legal filing decisions with the accountant.

## Receipt

Owner correction on **2 November 2026**: the supplied restaurant menu card prices exclude GST. New bills add **CGST 2.5% + SGST 2.5%** to the unchanged menu base prices. For ₹170: taxable ₹170.00 + CGST ₹4.25 + SGST ₹4.25 = **₹178.50**, before optional post-tax rounding (disabled by default). Keep GSTIN `33BPFPD3960P2ZN`. This supersedes the 28 October inclusive-price assumption for future billing only. Keep inclusive/exclusive price basis configurable and saved with each sale; all historical inclusive amounts/identities/payments and backup formats remain supported.

Use `resources/references/receipt-style-reference.jpeg` for the visual hierarchy: prominent shop branding, compact contact area, bill/date/time/cashier, product/quantity/rate/amount columns, large net amount, item/quantity summary and optional merchant UPI QR.

This reference belongs to another shop. Never reuse its name, phone/address, barcode content or payment QR. The restaurant's own values must be configured. No need to duplicate the vegetable weight-selling behavior merely because the reference lists grams/kg.

Owner alignment confirmation on 2 November 2026: print CGST/SGST figures directly beneath the RATE column, with labels on the left. Keep the saved GST basis/components/total unchanged on reprint.

Use 80 mm as the selected roll width; determine the actual printable dot width during the printer test. Do not assume all 80 mm is printable. Render Tamil/rupee/branding through a tested raster path when raw ESC/POS code-page support is insufficient. Close visual font matching is possible; exact identity is unknown without original font/template assets and must be accepted using sample paper output.

If current composition status is confirmed, use the appropriate Bill of Supply configuration and declaration instead of separately charging customer GST. Preserve a configurable regular-tax path if the accountant establishes a different current status. Historical GSTR-4 is supporting evidence, not a live registration lookup.

## Backups and setup

Provide a complete local backup of database, configuration and product/logo images, with an export/share/save mechanism. Restore validates format/version and integrity before replacing active data. Demonstrate restore in a separate disposable test installation. Monthly accounting files do not replace this backup.

Setup values not yet supplied: final restaurant logo, individual dish images, verified address/phone, merchant UPI details, exact receipt font source and current tax status. Implement editable setup and safe placeholders. Do not invent real payment or business identity data.
