# Phase 4 Query Plans

## Index Audit

All 29 indexes named in `VGL_POS_Architecture_Review.md` section 5.2 were
already present in Alembic migrations `0002` through `0008`; Phase 4 does not
drop and recreate established unique indexes. Migration `0013` adds four
compound hot-path indexes:

| Index | Query supported |
|---|---|
| `idx_products_company_created` | Tenant product keyset page |
| `idx_customers_company_created` | Tenant customer keyset page |
| `idx_sales_company_branch_created` | Branch sale keyset page |
| `idx_sales_company_branch_status_date` | Revenue and completed-sale date range |

PostgreSQL creates and drops all four with `CONCURRENTLY`. The migration also
rebuilds `mv_daily_sales_summary` with `total_cess`, preserving exact daily GST
totals, and recreates the unique index required for concurrent refresh. The
automated migration test proves `head -> 0012 -> head -> base -> head`.

## Captured Local Plan

The final 100,000-product SQLite barcode plan is included because it diagnosed
and prevented two superficially indexed but slow query shapes:

```text
SEARCH products USING INTEGER PRIMARY KEY (rowid=?)
SCALAR SUBQUERY 1
SEARCH products USING INDEX idx_products_barcode (company_id=? AND barcode=?)
SCALAR SUBQUERY 2
SEARCH product_barcodes USING INDEX uq_product_barcodes_code
  (company_id=? AND barcode=?)
```

Raw lookup timing for this plan was 0.056 ms median and 0.123 ms p99 over 1,000
samples. The full endpoint measured 4.989 ms p99 over 500 requests.

## PostgreSQL Before And After

`scripts/capture_query_plans.py` runs `EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)`
for these ten queries against the required 100k/5k/2k dataset:

1. Primary or alternate barcode lookup
2. Product keyset page
3. Exact tenant SKU lookup
4. Customer keyset page
5. Exact tenant phone lookup
6. Branch sale keyset page
7. Seven-day grouped revenue
8. Materialized daily summary lookup
9. Customer sale history
10. Exact invoice lookup

The nightly workflow downgrades only migration `0013`, captures
`query-plans-before.txt`, upgrades to `head`, runs `ANALYZE`, and captures
`query-plans-after.txt`. The after capture fails if any plan contains
`Seq Scan` or lacks an index operation. Both files are retained in the
`phase4-load-results` artifact.

PostgreSQL plan text is not embedded here because Docker and PostgreSQL are not
installed on the local workstation. This avoids presenting SQLite output or
fabricated text as `EXPLAIN (ANALYZE, BUFFERS)` evidence. The exact command run
by CI is:

```bash
uv run alembic downgrade 0012
uv run python scripts/capture_query_plans.py --label before > query-plans-before.txt
uv run alembic upgrade head
uv run python scripts/capture_query_plans.py --label after > query-plans-after.txt
```
