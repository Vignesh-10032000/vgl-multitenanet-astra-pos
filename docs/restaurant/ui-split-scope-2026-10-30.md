# UI/report separation and split tender — 30 October 2026

Owner requested original-dashboard design reuse, bilingual metric/export labels, distinct Dashboard/Sales/Reports screens with independent date/payment defaults, touchscreen billing without quick keys/F-key strip, readable cart/category layout and aligned customer entry. KOT remains future-only and is not implemented.

The original request limited changes to UI/queries. In this chat the owner explicitly clarified **“Include split payment and ledger changes now”**. This authorizes the minimal schema migration and atomic multi-tender checkout, plus the necessary receipt/report/export/backup adaptations. GST calculations, saved sale snapshots, final numbering and native print/USB/hardware code remain preserved.

Split amounts are ledger payment rows: cashier-recorded UPI is exact, excess cash is change, allocations equal the saved bill. Payment-filtered totals use the selected payment share and never duplicate a mixed bill or its lines. Returns record actual Cash/GPay channels; partial returns on mixed bills require explicit amounts. Existing single-tender data and version-1 backups migrate without changing historical totals or numbering.

Verification must include atomic second-tender rollback, duplicate retry, migration and old/new backup restore, mixed-filter reconciliation, user-specified cash/UPI/cancelled scenarios, independent date defaults, UI separation/layout, readable Tamil screen/receipt/PDF and unchanged tax fixtures. Hardware printing remains a separate device check.
