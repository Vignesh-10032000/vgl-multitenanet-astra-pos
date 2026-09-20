"""Capture the ten Phase 4 PostgreSQL hot-query execution plans."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

_QUERIES: Mapping[str, str] = {
    "01_barcode_lookup": """
        SELECT p.* FROM products p
        WHERE p.company_id = 1 AND p.deleted_at IS NULL
          AND p.id = COALESCE(
            (SELECT id FROM products
             WHERE company_id = 1 AND deleted_at IS NULL AND barcode = 'PERF-00001'
             LIMIT 1),
            (SELECT product_id FROM product_barcodes
             WHERE company_id = 1 AND deleted_at IS NULL AND barcode = 'PERF-00001'
             LIMIT 1)
          )
    """,
    "02_product_page": """
        SELECT * FROM products
        WHERE company_id = 1 AND deleted_at IS NULL
        ORDER BY created_at, id LIMIT 20
    """,
    "03_product_sku": """
        SELECT * FROM products
        WHERE company_id = 1 AND deleted_at IS NULL AND sku = 'PERF-SKU-00001'
    """,
    "04_customer_page": """
        SELECT * FROM customers
        WHERE company_id = 1 AND deleted_at IS NULL
        ORDER BY created_at, id LIMIT 50
    """,
    "05_customer_phone": """
        SELECT * FROM customers
        WHERE company_id = 1 AND deleted_at IS NULL AND phone = '8000000001'
    """,
    "06_sale_page": """
        SELECT * FROM sales
        WHERE company_id = 1 AND branch_id = 1 AND deleted_at IS NULL
        ORDER BY created_at, id LIMIT 20
    """,
    "07_revenue_week": """
        SELECT business_date, COUNT(id), SUM(net_amount) FROM sales
        WHERE company_id = 1 AND branch_id = 1 AND sale_status = 'COMPLETED'
          AND deleted_at IS NULL
          AND business_date BETWEEN CURRENT_DATE - INTERVAL '6 days' AND CURRENT_DATE
        GROUP BY business_date ORDER BY business_date
    """,
    "08_daily_summary": """
        SELECT * FROM mv_daily_sales_summary
        WHERE branch_id = 1 AND business_date = CURRENT_DATE
    """,
    "09_customer_sales": """
        SELECT * FROM sales
        WHERE company_id = 1 AND branch_id = 1 AND customer_id = 1
          AND deleted_at IS NULL
        ORDER BY created_at, id LIMIT 50
    """,
    "10_invoice_lookup": """
        SELECT * FROM sales
        WHERE company_id = 1 AND deleted_at IS NULL
          AND invoice_number = 'PERF/000000001'
    """,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", choices=("before", "after"), required=True)
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    database_name = make_url(database_url).database or ""
    if not database_name.endswith("_test"):
        raise RuntimeError("Query-plan capture is restricted to databases ending in '_test'.")

    engine = create_engine(database_url, pool_pre_ping=True)
    output = [f"# Phase 4 query plans: {args.label}\n"]
    failures: list[str] = []
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("ANALYZE"))
        for name, query in _QUERIES.items():
            rows = connection.execute(text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT) {query}"))
            plan = "\n".join(str(row[0]) for row in rows)
            output.extend((f"\n## {name}\n", plan, "\n"))
            if args.label == "after" and ("Index" not in plan or "Seq Scan" in plan):
                failures.append(name)
    sys.stdout.write("\n".join(output))
    if failures:
        raise RuntimeError(
            "Post-index plans must use indexes without sequential scans: " + ", ".join(failures)
        )


if __name__ == "__main__":
    main()
