# GST compliance mapping

This is an engineering control map, not tax advice. The compliance owner must re-check notifications and portal advisories before each filing period.

| Requirement | VGL POS control | Evidence |
| --- | --- | --- |
| CGST Rule 46 invoice particulars | Immutable supplier/customer snapshots, financial-year series, HSN/UQC, place of supply, taxable value, rate and tax splits; configurable template validation | Invoice service and Rule 46 template tests |
| CGST Rule 48 / e-invoice | Provider-neutral schema 1.1 mapping, durable IRN queue, signed QR storage, duplicate lookup, cancellation guard and reconciliation | Phase 9 schema/queue/API tests |
| GSTR-1 B2B | Registered-recipient invoices grouped with rate-wise tax detail | 30-invoice hand-calculated fixture |
| GSTR-1 B2CL | Inter-state unregistered invoices above ₹1 lakh (current portal threshold) | statutory report threshold and fixture |
| GSTR-1 B2CS | Remaining consumer supplies consolidated by supply type, place and rate | report reconciliation tests |
| Credit/debit notes | Registered-recipient credit notes in CDNR with immutable original-sale tax facts | returns and GSTR-1 tests |
| HSN summary | Separate B2B and B2C HSN/UQC quantity/value/tax summaries | workbook/JSON tests |
| Documents issued | Series from/to, total, cancelled and net issued; mandatory portal table from May 2025 | GSTR-1 document-series tests |
| GSTR-3B | Output-tax summary derived from the same fiscal snapshots, with reconciliation guard | statutory report tests |
| Composition scheme | Blocks tax-invoice/e-invoice behavior that is incompatible with composition configuration | compliance settings tests |
| Auditability | Append-only audit rows; runtime role has SELECT/INSERT only; UPDATE denial tested in PostgreSQL | `tests/security/test_operational_security.py` |

Primary references reviewed for this mapping:

- [CBIC tax invoice, credit and debit note rules](https://cbic-gst.gov.in/gst-invoice-rules.html)
- [GST Portal GSTR-1 guide](https://tutorial.gst.gov.in/userguide/returns/GSTR_1.htm)
- [GST Portal creation of outward supplies return](https://tutorial.gst.gov.in/userguide/returns/Creation_of_Outward_Supplies_Return_in_GSTR-1.htm)
- [GSTN April 2025 HSN Table 12 and Documents Issued advisory](https://tutorial.gst.gov.in/downloads/news/updated_advisory_hsn_table12_25042025.pdf)
- [Notified e-invoice schema](https://einvoice6.gst.gov.in/content/notified-e-invoice-schema/)

Operational acceptance still requires government GST Offline Utility validation of generated files and a Tally trial-company import. Those are manual gates and are not implied by automated tests.
