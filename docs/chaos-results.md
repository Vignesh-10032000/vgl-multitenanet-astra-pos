# Phase 10 chaos evidence

These deterministic tests use disposable databases and synthetic data. They are safe CI evidence, not a claim that a full staging infrastructure exercise has been performed.

| Failure | Injection | Observed behavior | Control/fix | Automated evidence |
| --- | --- | --- | --- | --- |
| PostgreSQL disconnect during checkout | Raise `OperationalError` at commit after the sale aggregate is built | No sale remains after rollback; caller receives a typed retry-safe checkout failure | Checkout now explicitly catches general SQLAlchemy failures, rolls back and increments `checkout_failures_total{reason="database_unavailable"}` | `tests/chaos/test_failure_recovery.py` |
| Redis unavailable | Point rate-limit storage at a closed port | Liveness remains 200 and carries a request ID | Flask-Limiter swallows storage errors and uses its in-memory fallback; database checkout is independent | `tests/test_smoke.py::test_p1a_1_health_survives_redis_outage` |
| Worker terminated with compliance row in processing | Age a PROCESSING e-invoice/e-way-bill record beyond the lease | Reconciliation returns it to retry processing; the sale remains committed | Durable database queue plus stale-processing recovery and idempotent provider lookup | `tests/integration/test_einvoice.py` |
| Report-artifact disk full | Raise `ENOSPC` from atomic temporary-file write | Job becomes FAILED with completion time/error and no completed artifact is exposed | Failure transaction is persisted and operator can create/retry a job after capacity recovery | `tests/chaos/test_failure_recovery.py` |

`scripts/chaos_exercise.sh` adds live Redis and worker stop/start coordination but refuses to run unless `CHAOS_DISPOSABLE_ENVIRONMENT=yes`. The database stop-during-Locust and full staging rollback remain supervised staging exercises; record their timings in the incident log before production acceptance.
