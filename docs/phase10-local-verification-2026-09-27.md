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
