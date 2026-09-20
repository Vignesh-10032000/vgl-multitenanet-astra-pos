# Phase 4 Performance Baseline

Measured on 2026-09-19/20 from the Phase 4 branch. Local measurements use the
file-backed SQLite test stack on Windows; PostgreSQL and Redis production-stack
measurements run in the scheduled `nightly-load` CI job.

## Regression Budgets

| Path | Prototype baseline | Phase 4 result | Enforced by |
|---|---:|---:|---|
| `GET /api/v1/sales?limit=20` | 55 queries | 1 query, budget <= 4 | `test_sales_list_stays_within_four_queries` |
| `GET /api/v1/customers?limit=50` | 7 queries | 1 query, budget <= 2 | `test_customer_list_stays_within_two_queries` |
| `GET /api/v1/reports/revenue?days=365` | 732 queries | 1 grouped query, budget <= 2 | `test_revenue_year_stays_within_two_queries` |
| `GET /api/v1/products/lookup?barcode=X` | No fast path | Exactly 1 query | `test_barcode_lookup_is_exactly_one_query` |
| Weighted inventory valuation | `1 + N` ledger queries | 1 set query | `test_weighted_inventory_valuation_is_one_set_query` |
| Collection DTO serialization | Not guarded | 0 lazy-load queries | `test_collection_dto_serialization_never_lazy_loads` |

The prototype figures above are the measured baselines supplied in the Phase 4
governing prompt. Phase 4 results are executable assertions, not copied target
values.

## Barcode Benchmark

Dataset: 100,000 products in one tenant, 250 requests in the required pytest
gate and a separate 500-request confirmation run after warm-up.

| Implementation | Median | p99 | Result |
|---|---:|---:|---|
| Correlated `OR EXISTS` lookup | Not retained | 103.896 ms | Failed |
| Indexed candidate IDs with outer `IN` | 18.690 ms | 29.925 ms | Failed |
| PK equality with indexed scalar probes | 2.564 ms | 4.989 ms | Passed `< 10 ms` |
| Final raw SQLite SQL, 1,000 samples | 0.056 ms | 0.123 ms | Indexed |

The benchmark includes the complete Flask request path, JWT verification,
permission guard, DTO construction, and JSON response. The raw-SQL row is shown
only to separate database time from HTTP/application overhead.

## Dataset And Load Gate

`scripts/seed_performance.py` refuses non-test databases and seeds:

| Entity | Count |
|---|---:|
| Sales | 100,000 |
| Products | 5,000 |
| Customers | 2,000 |

The seed completed locally against a disposable SQLite database in 22.4 seconds.
The scheduled CI workload uses PostgreSQL 16, Redis 7, four Gunicorn workers,
and 50 concurrent cashier users. Each user searches, scans five barcodes,
quotes, and checks out, then waits six seconds. The gate fails unless checkout
p99 is below 500 ms and the error rate is zero.

Local Docker/PostgreSQL execution was unavailable because neither Docker nor
PostgreSQL binaries are installed on the workstation. Production-stack numbers
must therefore be taken from the `phase4-load-results` nightly artifact; no
SQLite figure is represented as PostgreSQL evidence.

## Reproduction

```powershell
uv run pytest tests/performance -v --basetemp "D:\vgl pos\.pytest-tmp"
```

```bash
VGLPOS_ALLOW_PERFORMANCE_SEED=1 uv run python scripts/seed_performance.py
uv run locust -f tests/load/locustfile.py --headless \
  -u 50 -r 5 -t 5m --host http://127.0.0.1:8000
```
