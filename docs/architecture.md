# VGL POS architecture

## System context (C4 level 1)

```mermaid
C4Context
  title VGL POS system context
  Person(cashier, "Cashier", "Bills customers and closes shifts")
  Person(manager, "Manager", "Controls stock, reports and exceptions")
  Person(accountant, "Accountant", "Files GST and reconciles books")
  System(vglpos, "VGL POS", "Multi-company retail POS and compliance system")
  System_Ext(irp, "GST Invoice Registration Portal", "IRN and e-way bill provider")
  System_Ext(gst, "GST Offline Utility", "Validates return exports")
  System_Ext(tally, "Tally", "Imports accounting vouchers")
  System_Ext(notify, "Receipt providers", "WhatsApp, SMS and email")
  Rel(cashier, vglpos, "HTTPS/PWA")
  Rel(manager, vglpos, "HTTPS")
  Rel(accountant, vglpos, "HTTPS and exports")
  Rel(vglpos, irp, "Schema 1.1 JSON over TLS")
  Rel(vglpos, notify, "Provider webhooks")
  Rel(accountant, gst, "JSON/XLSX")
  Rel(accountant, tally, "XML")
```

## Containers (C4 level 2)

```mermaid
C4Container
  title VGL POS containers
  Person(user, "Store user")
  Container(web, "Browser PWA", "Vanilla JS, IndexedDB", "Online/offline counter workflow")
  Container(api, "Flask API", "Python 3.12", "RBAC, pricing, inventory, GST and reporting")
  Container(worker, "Celery workers", "Python 3.12", "Receipts, reports and compliance retries")
  ContainerDb(db, "PostgreSQL", "PostgreSQL 16", "Tenant data, immutable fiscal snapshots and audit log")
  ContainerDb(redis, "Redis", "Redis 7", "Broker, cache, rate limits and feature flags")
  Container(obs, "Observability", "Prometheus, Grafana, Sentry", "Metrics, dashboards and scrubbed exceptions")
  Rel(user, web, "Uses")
  Rel(web, api, "JSON/JWT over HTTPS")
  Rel(api, db, "SQL/TLS")
  Rel(api, redis, "RESP/TLS")
  Rel(worker, db, "SQL/TLS")
  Rel(worker, redis, "Celery")
  Rel(api, obs, "JSON logs, metrics, scrubbed events")
  Rel(worker, obs, "JSON logs, scrubbed events")
```

## Key boundaries

The browser is untrusted. Prices, tax, permissions, tenant/branch scope, stock, document numbers and totals are recomputed server-side. Mutations use idempotency keys; offline sales add a signed terminal-bound payload and UUID. Services own transactions and publish only after commit.

PostgreSQL is the system of record. Sales preserve tax/cost/supplier/batch snapshots. Stock and audit ledgers are append-only; the runtime role has no audit update/delete privilege. Celery work begins from durable database rows, so worker termination cannot lose a report or compliance request.

The application emits no migration during boot. A release migration job completes before readiness-gated rolling pods change image. Nightly encrypted dumps and continuous encrypted WAL archives target a private object store; the age identity resides in the secret manager, never beside backups.

Every request receives a request ID. Authentication adds user, company and branch context. Structured logs, bounded-label Prometheus metrics, privacy-scrubbed Sentry events, two Grafana dashboards and linked alert runbooks form the operations surface.
