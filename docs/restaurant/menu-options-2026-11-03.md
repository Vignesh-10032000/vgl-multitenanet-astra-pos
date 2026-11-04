# Regular / Parcel products and fixed kilogram portions — 3 November 2026

The owner requested a Regular / Parcel choice in Add Product, with products appearing only in their assigned filter. The owner clarified that kilograms describe a fixed menu portion and that the entered selling price remains fixed until changed through Edit.

## Behavior

- Add/Edit Product now includes Menu type (Regular or Parcel) and optional Kilograms per portion. For example, 0.5 kg can have its own ₹230 selling price, independent of a 1 kg product's price. This is a price for the whole portion; billing still counts portions. Existing GST configuration applies on top of the menu base price.
- Products and Billing include All / Regular / Parcel filters. Billing combines menu type with its existing category/search controls. New products inherit the selected Products filter and can be reassigned through Edit. All shows both types.
- Existing Parcel-category products default to Parcel, other existing products to Regular. Explicit owner assignments override category inference. Existing categories, product IDs/prices, photos and historical sales are retained.
- Kilograms accept exact decimal strings with gram precision, from 0.001 to 9999 kg. The fixed portion is stored in the existing portion field. Editing an existing `1/2 kg` product without changing its weight retains that exact label and price. No proportional pricing is introduced.

## Persistence and compatibility

Menu type uses the existing SQLite local metadata store (`drafts`, key `local:product-menu:<product-id>`). Saving the product and its assignment is one transaction. Complete backups already contain this store, and inspection now validates the new assignment values. No schema change or ledger migration is needed; schema version remains 3 and v1/v2/v3 backup support remains intact. No photo install marker is reset. Backup validation continues to use isolated in-memory sql.js on native Android, preserving the safety correction documented in the Pad Go handoff.

## Verification

- 92 restaurant Node checks passed, including three new checks for exact kg input/legacy labels, atomic assignment rejection, independent pricing, historical-sale preservation and complete restore.
- 11 frontend checks passed, including all 200 shared tax-parity scenarios.
- All 62 distinct browser scenarios verified: full run 61 passed / one failed, followed by both GST scenarios passing on a focused rerun (2/2). The failed case clicked Reprint after reload before workspace actions were bound; its test now explicitly waits for SQLite readiness. The application build did not change between these runs. The two new scenarios cover product creation/filter isolation, combined category/search, restart/draft durability, price/menu-type edits, old half-kg labels and corrected invalid weight input. Six existing billing geometry cases cover desktop, tablet, portrait phone and short landscape.
- JS lint and production Vite build passed. Scoped security scan: 55 files / four rules / zero findings.
- Android debug assembly and lint passed; zero lint errors / 19 existing warnings. Native Java tests were not rerun because native business logic is unchanged.
- Signature verified with the existing debug certificate; production package `in.vgl.restaurant`, version 1.0.19 (20). All 67 packaged web files match the built files byte for byte. APK hash and individual asset hashes: `menu-options-build-2026-11-03.json`.
- Corrected Billing and product-form screenshots were visually reviewed in `test-results/product-options-billing.png` and `test-results/product-options-form.png`.

Candidate: `artifacts/restaurant-pos-1.0.19-debug.apk`. This update has **not been installed or device-tested**. No owner device, live ledger, credentials, image files or shared backup documents were accessed or changed. TVS performance/touch acceptance, native lifecycle and physical printing remain unverified for this build.
