# VGL POS operations runbook

## Service objectives

- Checkout availability target: 99.9%; checkout p99 target: under 1 second.
- Recovery point objective (RPO): 15 minutes, provided by continuous WAL archival.
- Recovery time objective (RTO): 1 hour. `scripts/restore_drill.sh` measures and fails above 3,600 seconds.
- Nightly backups remain for 30 days; first-of-month archives remain for eight years. Apply `ops/backup/object-storage-lifecycle.json` to the private object-storage bucket.

Every incident must record start/end time, affected companies/branches, request IDs, commands run, feature flags changed, recovery evidence, and follow-up owner. Never paste GSTINs, phone numbers, customer names, tokens, or raw invoice payloads into chat or tickets.

## First response

1. Declare an incident owner and freeze unrelated deployments.
2. Check `/health`, `/ready`, the technical dashboard, deploy history, PostgreSQL, Redis, Celery workers, disk, and the most recent backup metric.
3. Correlate JSON logs using `request_id`, then narrow with `company_id` and `branch_id`. These fields are present on every line.
4. Disable only the affected risky workflow if needed:
   `flask --app vglpos.app feature-flag einvoice disable`, `eway_bill disable`, or `report_jobs disable`.
5. Preserve logs and database evidence. Do not edit invoice, stock-ledger, or audit rows.

## Checkout latency

Alert: p99 checkout above one second for five minutes.

Check database locks and `db_pool_in_use`, CPU, disk latency, current rollout, and slow-query plans. Stop a bad rollout; scale application workers only if the database has pool headroom. Verify with one test checkout and the checkout latency panel before resolving.

## HTTP errors

Alert: five-minute 5xx rate above one percent. Group logs by route and error type, find a request ID, and inspect Sentry after confirming identifiers are scrubbed. If the error began at a release, use the rollback checklist below.

## Offline queue

Alert: more than 100 offline operations for five minutes. Verify WAN stability and terminal clock, leave local queues intact, and restore connectivity. Replays are idempotent by offline UUID. Do not ask staff to re-enter bills. Confirm the gauge returns to zero and compare affected invoices and stock ledgers.

## E-invoice queue

Alert: more than 50 pending records for five minutes. Check IRP availability and credentials, retry age, dead letters, and `/api/v1/compliance/reconciliation`. Disable `einvoice` during sustained provider failure; committed sales remain durable and the reconciliation task backfills missing records. Re-enable, run reconciliation, and verify IRNs without logging GSTINs.

## Backup failure

Alert: no successful backup for 26 hours. Check `pg_dump`, `age`, object-store authorization, capacity, and the node-exporter textfile. Never copy the age identity into the backup bucket. After repair, run `scripts/backup_postgres.sh`, then `scripts/restore_drill.sh`; a successful upload alone is not recovery proof.

## Disk capacity

Alert: filesystem above 80% for ten minutes. Identify growth without deleting audit, invoice, database, or backup data. Rotate managed logs through the platform, move report artifacts under their retention policy, and add capacity. A full report-artifact disk marks the durable job failed for an operator retry.

## Replication lag

Alert: PostgreSQL replica lag above 30 seconds for five minutes. Check network, WAL receiver/replay state, long replica queries, disk, and WAL retention. Do not promote until the database incident procedure confirms timeline and data-loss bounds.

## Restore drill

The monthly CI job creates an encrypted backup, restores the latest archive into a uniquely named scratch database, compares row counts plus sales/stock sums, runs tax/invoice/stock/e-invoice invariants, prints measured RTO, and tears the database down. Production drill inputs are `DRILL_ADMIN_URL`, `AGE_IDENTITY_FILE`, and either `BACKUP_BUCKET` or `BACKUP_OUTPUT_DIR`.

Success requires matching manifests, every invariant passing, and elapsed time under one hour. Store the CI artifact/log as monthly evidence. The 15-minute RPO depends on the separately monitored `archive_command`; sample-restore WAL quarterly.

## Deploy and rollback

`scripts/deploy.sh` requires an `@sha256` image digest, runs the migration job first and waits for success, then changes the application image, waits for readiness-gated rolling completion, and smoke-checks `/ready` plus `/health` through a temporary local service port-forward. Set `POST_DEPLOY_SMOKE_PORT` only when the default local port `18080` is occupied. Application startup never runs migrations.

Pre-deploy checklist: all quality/security/browser gates are green; the immutable image digest and audit results are recorded; migration upgrade and downgrade behavior is reviewed; current backup/restore evidence meets policy; configuration and managed secrets are present; risky-feature defaults are confirmed; the previous digest is known; and any database downgrade is explicitly certified data-safe.

Post-deploy smoke checklist: confirm the script's `/ready` and `/health` probes, then use the synthetic staging tenant to verify login, quote, checkout, receipt, report-job completion, compliance queue processing and authenticated metrics. Confirm dashboards receive the new version without an error-rate or latency alert. Do not create test financial documents in a production tenant.

Rollback checklist: incident approval; identify the previous digest; read that release's migration downgrade notes; set `CONFIRM_ROLLBACK=yes` and `PREVIOUS_IMAGE`; set `ROLLBACK_DATABASE=yes` only when `alembic downgrade -1` is certified data-safe; run `scripts/rollback.sh`; validate `/ready`, login, quote, checkout, receipt, report job, e-invoice queue, and metrics. Record all results. A full staging rollback remains a manual release gate.

## Chaos and audit exercises

Run `uv run pytest tests/chaos -q` for deterministic database-disconnect and full-disk injection. `scripts/chaos_exercise.sh` coordinates live Redis and worker stop/start checks in a disposable environment; the database stop-during-checkout case remains a supervised staging drill. Expected behavior: checkout rolls back atomically; Redis rate limiting degrades without blocking health; stale compliance work recovers; disk errors persist a failed report job.

For an audit walkthrough, select a sale and follow its append-only `audit_log` entries, invoice, payments, stock ledger, batch allocations, return batches, and e-invoice. Use `request_id` to correlate the initiating request. The application database role may select/insert audit rows but an update must fail with SQLSTATE `42501`.
