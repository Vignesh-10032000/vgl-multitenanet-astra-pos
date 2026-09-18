# Phase 1B design notes

The official `VGL_POS_Architecture_Review.md` is the schema source of truth. The
following narrow additions resolve conflicts between its illustrative SQL and
the mandatory Phase 1B/Phase 1D invariants. No retail policy, price, result, or
tenant identity has been invented.

## Mandatory invariants applied to illustrative-DDL exceptions

Section 5.1 and the Phase 1B prompt require a BIGINT surrogate key and the full
audit/soft-delete/row-version set on every table. Several child and mapping
tables in the illustrative SQL use composite keys or omit audit columns. The
models and migrations apply the mandatory invariant consistently. Tenant-owned
child/mapping tables also carry `company_id`, avoiding joins merely to establish
the tenant boundary.

The two truly global lookup tables are `permissions` and `hsn_codes`; both are
audited but do not carry `company_id`.

The supplied DDL makes `hsn_codes` global while `default_tax_rate_id` points to
the tenant-scoped `tax_rates` table. That cross-scope reference is implemented
as specified, but later write services must prevent one company's rate from
being selected as another company's HSN default. A future approved DDL revision
should either tenant-scope HSN rows or separate global slab definitions from
company rate schedules.

The universal soft-delete rule makes every natural-key unique index partial,
including invoice and credit-note numbers. This technically permits key reuse
after a soft delete. Fiscal services must never soft-delete or reuse issued
document numbers; permanent fiscal-number uniqueness would be safer in a future
approved DDL revision.

## Fields required by later approved phases

- `tax_rates.effective_from` and `effective_to` retain the pre-GST-2.0 and
  GST-2.0 schedules required by the Phase 1B seed command and Phase 1C rate
  history tests.
- `products.on_hand`, `reserved_quantity`, and `allow_negative_stock` are
  required by the explicitly specified Phase 1D inventory and checkout
  services. All are Decimal quantities with database checks.
- `sales.offline_uuid` and its tenant-scoped partial unique index provide the
  Phase 1D checkout idempotency key.
- `sales.shift_id` is created in the documents migration and gains its explicit
  foreign key after `shifts` is created in migration 0008.

## Audit foreign keys and partitioning

Audit actor columns reference `users(id)` with `ON DELETE RESTRICT`. The core
tenancy tables precede `users`, so migration 0003 adds those foreign keys after
creating the identity tables. PostgreSQL receives the range-partitioned
`audit_log` plus the three specified example partitions and a default partition
so audit writes do not fail after September 2026.

SQLite receives an ordinary audit table and ordinary daily-summary view for
hermetic structural tests. PostgreSQL remains the authoritative server dialect.

## Indian state codes

The target DDL has no state-code lookup table. The 37 immutable GST jurisdiction
codes therefore live in `vglpos.domain.reference.STATE_CODES`; the seed command
verifies the catalogue count and reports it while persisting permissions and
company-scoped dated GST rates.

## Index creation

Indexes on products, barcodes, customers, sales, sale items, credit notes,
stock batches, the stock ledger, and the daily-sales materialized view use
PostgreSQL `CREATE INDEX CONCURRENTLY`. Their migration helpers enter Alembic
autocommit blocks because PostgreSQL prohibits concurrent index creation inside
a transaction. SQLite uses ordinary indexes for the hermetic migration tests.
