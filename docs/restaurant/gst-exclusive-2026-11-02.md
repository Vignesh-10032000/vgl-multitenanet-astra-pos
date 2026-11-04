# GST added to restaurant menu prices — 2 November 2026

## Owner instruction and behavior

The owner corrected the pricing assumption: the restaurant's supplied price card excludes GST. New bills now add the existing CGST 2.5% and SGST 2.5% to unchanged menu base prices. ₹170.00 base + ₹4.25 CGST + ₹4.25 SGST = ₹178.50. A ₹10 discount reduces the base to ₹160 and gives ₹168 including GST. Optional rupee rounding remains the saved setting and occurs after GST; the default is disabled. No tax-rate/GSTIN change was requested.

This supersedes the 28 October inclusive-price assumption for future billing. Previously issued inclusive bills retain their original item prices, GST components, totals, payments, customer/store identities, timestamps and final bill numbers. Product names/photos, one-time photo markers, restaurant/VGL branding, language/theme controls, owner access and append-only backup behavior are preserved.

## Implementation

- `restaurant/domain.js`: exact integer/BigInt inclusive and exclusive calculations, discount allocation before GST, post-tax round-off, overflow and invalid-basis rejection. Unknown historical price basis defaults to inclusive.
- `restaurant/schema.js` / `repository.js`: schema v3 snapshots `tax_inclusive` on each sale and line, with matching SQLite arithmetic constraints. The upgrade stages constrained financial tables and copies original rows inside the existing transaction, with foreign keys enabled. Old records receive only the explicit inclusive flag; other historical cells remain unchanged. A failed migration rolls back everything. Current settings receive the owner-corrected exclusive mode once through `gst_pricing_revision`; subsequent saved choices are respected. No live ledger was accessed during development.
- `restaurant/backup.js`: strict v1/v2 shape validation before upgrade to v3, explicit historical inclusive flags, saved basis/identity reconciliation and complete scratch-database validation. Original backups are never rewritten or deleted.
- `restaurant/index.html`, `app.js`, `preferences.js` and the existing `pos.js`: editable GST price basis in Settings; billing identifies menu prices as plus GST in English/Tamil. Cards retain the restaurant's base prices; checkout uses the GST-added total.
- `restaurant/documents.js` / `exports.js`: new exclusive receipts show taxable value, added-GST explanation and both components. Existing inclusive receipts retain their rendering. CSV/XLSX/PDF invoice datasets use the neutral GST amount heading plus an explicit saved price-basis column. Item totals/payments/report filters retain exact reconciliation.
- Defaults, requirements, acceptance checks and AGENTS.md record the latest owner correction. Legacy inclusive money/tax regressions remain intact and use an explicit inclusive fixture; fresh-default/upgrade tests separately exercise added GST. `tests/restaurant/fixtures/schema-v2.sql` is the exact old schema, used for real SQLite and WASM upgrade tests.

## Verification status

- VERIFIED: 92 Node/frontend checks (87 existing + 5 new), including 1,500 new generated exclusive-GST cases and the retained inclusive/property/backup/export/ledger checks.
- VERIFIED: five new Node scenarios cover saved snapshots/idempotency, discounted/odd-paise/post-tax rounding, real v2 upgrade, rollback of a partly executed migration, v1/v2 backup compatibility, mixed historical/current accounting, full restore and corrupt price-basis rejection.
- VERIFIED: two new browser scenarios exercise fresh defaults, cash/change/split payment, menu prices, receipt/reprint/reload, complete image backup validation, and an actual v2 SQLite file migrated in WASM without changing the old bill or reusing its number.
- VERIFIED: independent SymPy rational identity and five exact price examples; `test-results/gst-exclusive-2026-11-02/sympy-verification.json`.
- VERIFIED: JavaScript lint and web build. This vanilla-JavaScript project has no configured standalone type-check phase.
- VERIFIED: the 80 mm receipt PDF was rendered and visually inspected, including ₹170 taxable / ₹4.25 CGST / ₹4.25 SGST / ₹178.50 total and ₹21.50 cash change. Browser PDF evidence does not establish physical printing.
- VERIFIED: 38 browser scenarios across the broad run and corrected targeted rerun: 37 initially passed; the old photo-price assertion was corrected, then photo and both new GST scenarios passed 3/3. No application source changed between those browser runs.
- VERIFIED: Android build/lint, zero errors / 19 existing warnings; 11 unchanged native unit tests reused their passing Gradle cache. Scoped security scan: 50 files / four rules / zero findings.
- VERIFIED: signed APK 1.0.16 (17), 16,027,251 bytes, SHA256 `5fb090155acb3e38a22855bc1f616352b64fe515e92ec8aeaa868f0519d06806`; all 58 packaged web assets match the final build. `git diff --check` passed.

Evidence: `test-results/gst-exclusive-2026-11-02/` includes billing/receipt PNGs, the rendered PDF/PNG, a disposable fixture backup and mathematical checks. The initial broad browser run caught one old photo-test expectation of ₹170; its fresh-default expectation was updated to ₹178.50 without weakening photo/removal/restore checks.

## Installation status and limits

Candidate version: 1.0.16 (17). The TVS was not detected by Windows/ADB during the owner's USB-install attempt or the development follow-up. No installation, uninstall, app-data clear, owner credential change, live restore, live sale or shared-backup deletion occurred. Native TVS schema migration/lifecycle/performance and physical printing remain NOT VERIFIED. Preserve the prior installed app and all live data when connection becomes available. Older APKs cannot open a v3 ledger; do not clear data or restore over a nonempty ledger to bypass the version check.
