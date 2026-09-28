# Phase 10 local verification — 2026-09-27

Scope: a disposable Docker Desktop stack on this workstation, with PostgreSQL 16,
Redis 7, the current application image, four Gunicorn workers, and synthetic data.
These results are not staging or government-system acceptance evidence.

| Gate | Result | Evidence |
| --- | --- | --- |
| Playwright Chromium | Passed | 6/6 billing, offline, shift, accessibility, paint, and screenshot tests. |
| PostgreSQL audit role | Passed | `tests/security -q`: 2/2, including SQLSTATE 42501 on audit-log UPDATE as `vglpos_app`. |
| Encrypted backup and restore | Passed | `age`-encrypted dump and manifest of 100,000 seeded sales; restore integrity and RTO checks passed in 10 seconds. |
| Full 150-user load, 15 minutes | **Failed latency gate** | 45,548 requests, 0 failures, 5,628 checkouts; checkout p99 = 7,300 ms against a `< 1,000 ms` gate. See `phase10-local-load-valid.html` and `phase10-local-load-valid_*.csv` at the repository root. |
| Redis outage | Passed locally | Paused Redis: `/health` 200, `/ready` 503; after unpause, `/ready` 200. |
| PostgreSQL disconnect during checkout | Passed locally | Checkout returned 409; sale count stayed 105,649 before/after; after reconnect, checkout returned 201 and count rose to 105,650. |
| Worker abrupt termination | Passed locally | Worker exited on SIGKILL (137), restarted, then completed `vglpos.reconcile_einvoices` in 0.407 s. |
| Report-artifact disk-full injection | Passed | `tests/chaos -q`: 2/2 deterministic tests. |

The first load attempt was stopped because the performance seed did not open a
shift, causing checkout 404 responses. `scripts/seed_performance.py` now seeds an
open shift. A one-user checkout smoke test then passed 25/25 requests, including
three successful checkouts, before the full run above. The aborted attempt's
`phase10-local-load_*.csv` files are **not** acceptance evidence.

The restore drill also exposed a `psql | head -1` pipeline that could terminate
`psql` before the later integrity statements ran. `scripts/restore_drill.sh` now
captures all output and compares the manifest row only after `psql` succeeds.

Still open: a supervised staging rollback and staging load/chaos confirmation;
government GST Returns Offline Tool validation; Tally trial-company import; and
NIC sandbox generation/cancellation plus signed-QR verification. No staging
Kubernetes configuration, Tally/GST utility installation, or NIC sandbox
configuration was present in this environment. Do not treat the local drills as
substitutes for these external gates.

## Checkout latency follow-up — 2026-09-28

The original 150-user dataset sent every cashier through one open shift, one
document series, and the same five product stock rows. A revised disposable
seed and Locust topology give 150 cashiers independent shifts, document series,
and five-product sets while retaining 100,000 historical sales, 5,000 products,
and 2,000 customers. Checkout was also reduced from 38 to 17 SQL statements in
a warmed local profile by reusing validated context, avoiding per-ledger flushes,
and allocating document numbers with one atomic UPDATE.

These changes are **not** a pass of the 150-user gate. Two-minute diagnostic
pilots on the same four-core/eight-thread workstation produced:

| Setup | Checkout p99 | Failures |
| --- | ---: | ---: |
| Revised topology, 4 synchronous workers, pre-optimization image | 11,000 ms | 0 |
| Revised topology, 4 workers × 8 threads, pre-optimization image | 5,300 ms | 0 |
| Revised topology, 4 workers × 8 threads, optimized image | 4,500 ms | 37 |

The optimized pilot's 9,252 requests included 32 failed product lookups, four
failed quotes, and one disconnected checkout. The application consumed about
5.6 CPU cores and PostgreSQL about 1.2 cores during that pilot; these are
capacity observations, not proof that the code will meet the target elsewhere.
The pilot CSVs are `phase10-perf2-pilot-*_*.csv` at the repository root.

The Python regression suite passed after the changes, including a test that
an inactive branch cannot bypass checkout validation. A fresh 15-minute run
could not be started on 2026-09-28 because Docker Desktop failed to initialize
its engine (stale `sailor-ingest.sock` startup error). The next acceptance run
must use a healthy, adequately provisioned staging stack, capture server and
database CPU/connection metrics, and satisfy both zero failures and checkout
p99 below 1,000 ms for the full 15 minutes. Government sandboxes remain a
separate subsequent gate.

### Docker recovery and capacity comparison — 2026-09-28

Docker Desktop subsequently recovered. Its data disk is on D:, and the app
was rebuilt from commit `1214589` as `vglpos:phase10-perf3`. A new disposable
PostgreSQL/Redis stack was migrated and seeded with the same 150-lane dataset.
The one-cashier smoke test completed four checkouts with no failures and a
checkout p99 of 100 ms.

| Local load | Duration | Checkouts | Failures | Checkout p99 |
| --- | ---: | ---: | ---: | ---: |
| 50 cashiers | 1 minute | 464 | 0 | 900 ms |
| 100 cashiers | 1 minute | 766 | 0 | 2,600 ms |
| 150 cashiers | 2 minutes | 1,300 | 0 | 3,700 ms |

The 150-cashier pilot recorded 10,901 total requests. At full load the app
used about 5.9 logical CPUs, PostgreSQL about 1.3, and Redis about 0.2 on a
machine with eight logical CPUs; the Locust generator also ran on that same
machine. Throughput stopped scaling as concurrency increased, so these results
point to a local capacity ceiling rather than a remaining single-row lock
convoy. The comparison CSVs are `phase10-perf3-*_stats.csv` at the repository
root. The 150-user HTML report is `phase10-perf3-pilot.html`.

The full 15-minute 150-user rerun with these changes remains **unperformed**;
the diagnostic p99 already misses its target. Short pilots cannot substitute
for the full gate. Run the app, database, and load generator on appropriately
provisioned separate machines, then tune capacity and repeat the complete gate
before beginning the GST/NIC sandbox work.
