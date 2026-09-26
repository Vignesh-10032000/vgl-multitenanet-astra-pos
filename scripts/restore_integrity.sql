\set ON_ERROR_STOP on

-- Machine-comparable row counts and monetary/stock sums.
\i scripts/backup_manifest.sql

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM sales
        WHERE round(taxable_amount + cgst_amount + sgst_amount + igst_amount + cess_amount + round_off, 2) <> net_amount
    ) THEN
        RAISE EXCEPTION 'sales tax reconciliation failed';
    END IF;
    IF EXISTS (
        SELECT company_id, invoice_number FROM sales
        WHERE deleted_at IS NULL GROUP BY company_id, invoice_number HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'duplicate active invoice numbers found';
    END IF;
    IF EXISTS (SELECT 1 FROM stock_batches WHERE quantity_available < 0) THEN
        RAISE EXCEPTION 'negative batch stock found';
    END IF;
    IF EXISTS (
        SELECT 1 FROM sale_items item LEFT JOIN sales sale ON sale.id = item.sale_id
        WHERE sale.id IS NULL
    ) THEN
        RAISE EXCEPTION 'orphan sale items found';
    END IF;
    IF EXISTS (
        SELECT 1 FROM e_invoices WHERE status = 'GENERATED' AND (irn IS NULL OR signed_qr_code IS NULL)
    ) THEN
        RAISE EXCEPTION 'generated e-invoice lacks IRN or QR data';
    END IF;
END
$$;
