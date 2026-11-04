# Original billing conversion — 29 October 2026

The active restaurant build now takes billing markup from `src/vglpos/web/templates/pos.html` and executes the adapted **original** `src/vglpos/web/static/src/js/pos.js`. This is the first original-frontend conversion slice. Products, Customers, Sales, Reports and Settings currently remain the previous restaurant management screens; their original frontend controllers have not yet been converted.

## Source conversion map

| Source | Retained/adapted behavior | Local boundary |
| --- | --- | --- |
| Original `pos.html` | Product/cart panels, customer selection, discount/totals, Pay, original payment dialog, quick cash, shortcuts, help, holds and quick-key forms | Vite `original-billing-template.js` extracts the content block into the existing restaurant shell at build/dev time. No Jinja or Flask runs in the APK; there is no duplicate billing HTML. |
| Original `pos.js` | Category/product selection; cart rows; exact quantity adjustment; focus; remove/clear with undo; debounced quoting; payment state; completion; hold/recall; quick keys; keyboard shortcuts | Services supplied by restaurant bootstrap: `Ledger`, `ImageStore`, saved receipt and reprint. The controller is modified in place, not copied into a third UI. |
| Original `payment-view.js`, `payment-display.js` | Original payment row rendering, received/balance/change display, exact BigInt tender summary | Cash/GPay only. Controller values remain CASH/UPI; the adapter persists `cash`/`upi`. No split tender, reference requirement or settlement-verification claim. |
| Original `data.js`, `i18n.js`, `ui.js`, `pos-icons.js` | Scaled-integer quantity arithmetic, exact money formatting, local labels, DOM/dialog/toast/icon utilities | English catalogue bundled locally through `installCatalogue`, instead of a Flask locale URL. `operationId` supports Android WebViews without `crypto.randomUUID`. |
| Original `main.css`, `pos.css` and bundled fonts | Existing panel arrangement, cart/payment styling and responsive rules | Restaurant overrides enlarge local photo tiles. Import ordering ensures the source CSS cannot override those additions. |
| `restaurant/billing-adapter.js` | Explicit translation from original string IDs, decimal strings and cart products into repository inputs | Validates whole independently priced portions. Uses `domain.js` integer paise/BigInt quote and payment functions, also used by committed sales. No fake inventory fields or server identifiers. |
| `restaurant/app.js` | Bootstrap, existing management screens, receipt preview, export/backup/restore and native print/save integration | Removed its separate menu/cart/quote/payment/checkout controller and their event handlers. Only the original controller owns billing. |
| `restaurant/repository.js` | Existing atomic ledger, immutable snapshots, operations, final FY numbering, corrections and consistent backup support | Added local held carts, atomic recall and quick-key preferences using the existing `drafts` table; no schema or historical sale migration. |
| Native `RestaurantDocumentsPlugin` | Existing PrintManager and Storage Access Framework routes | Extracted `DocumentWriter`: success is resolved only after write, flush **and close** succeed; executor rejection is explicit. No direct USB plugin introduced. |

Removed from the converted controller/template: server/session bootstrap, tenant/user/branch cart keys, mandatory shifts and cash-drawer counting, stock validation/badges/deductions, server quotes/payment preview/checkout, server receipt navigation, provisional/outbox synchronization and barcode/weighing dependencies. Portion quantities remain. Holds and quick keys remain and are stored locally.

## Money, state and persistence

- Existing 200 tax parity fixtures and original payment/quantity checks remain. The restaurant quote uses the existing local ledger's inclusive-tax rounding/allocation policy, not an unreviewed replacement with the old retail tax engine. Both preview and save use that same local calculation boundary. ₹170 = ₹161.90 taxable + ₹4.05 CGST + ₹4.05 SGST, with ₹30 change on ₹200 cash.
- GST defaults, `gst_setup_revision`, settings upgrades and saved historical snapshots are preserved. No accountant reconfirmation or training reset was introduced.
- Product/customer identifiers remain strings, including seeded `menu-001` and generated UUIDs. Photos resolve through local image storage. Existing restaurant drafts/backups also restore into the converted cart.
- The controller captures draft values before queueing, waits for pending writes before checkout, locks repeated completion attempts, and clears the payable cart immediately after a successful commit. Receipt-render/print failure cannot roll the sale back or create another sale.
- Quotes invalidate immediately on cart/discount/customer changes. Quantity focus no longer destroys its input while typing. Undo callbacks are scoped to the current billing operation; a callback from a completed bill cannot restore sold items.
- Hold removes the durable active draft in the same transaction as inserting the held bill. Recall transfers it back atomically, refuses to overwrite another active cart and serializes against pending draft writes. Preferences/holds remain covered by complete snapshots.
- Reprint resolves a saved sale through SQLite, including after reload. Print attempts remain separate audit records; a submitted dialog is not proof of paper output.

## Verification boundary

See `quality-gate-2026-10-29.md` for fresh evidence and tooling evaluation. See `device-acceptance.md` for remaining native/hardware work. The original management screens still require incremental conversion. The original Flask asset build remains for existing helper/asset regression checks; it is not the standalone runtime entry point for this converted controller.
