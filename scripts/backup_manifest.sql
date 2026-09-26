SELECT json_build_object(
    'sales_count', (SELECT count(*) FROM sales),
    'sales_net_sum', (SELECT coalesce(sum(net_amount), 0)::text FROM sales),
    'sale_items_count', (SELECT count(*) FROM sale_items),
    'stock_batches_count', (SELECT count(*) FROM stock_batches),
    'stock_quantity_sum', (SELECT coalesce(sum(quantity_available), 0)::text FROM stock_batches),
    'audit_count', (SELECT count(*) FROM audit_log),
    'einvoice_count', (SELECT count(*) FROM e_invoices)
)::text;
