# Deployment Security

## Separate database identities

Use two PostgreSQL roles in production:

- A migration owner runs Alembic and owns schema objects. Its credentials are
  available only to the release job.
- `vglpos_app` runs Flask, Celery, and scheduled application work. It has DML
  access to domain tables but only `SELECT` and `INSERT` on `audit_log`.

After `alembic upgrade head`, run the checked-in grant script as the database
owner:

```powershell
psql $env:MIGRATION_DATABASE_URL --set=app_role=vglpos_app `
  --file scripts/configure_app_role.sql
```

Set the application `DATABASE_URL` to the `vglpos_app` credential. Set its
password out of band with PostgreSQL SCRAM authentication; never add it to the
SQL script, repository, image, or command history. Rerun the grant script after
each migration so new tables remain inaccessible until explicitly classified.

The Phase 2 migration also installs a database trigger that rejects every
`UPDATE` and `DELETE` against `audit_log`. The restricted role is the primary
least-privilege boundary; the trigger is defense in depth, including for an
accidentally over-privileged session.

## Runtime secrets and transport

- Supply independent, randomly generated `SECRET_KEY` and `JWT_SECRET_KEY`
  values of at least 32 characters.
- Keep PostgreSQL and Redis on private networks and require TLS outside a
  single-host deployment.
- Do not expose the migration identity to application containers.
- Back up the audit partitions with the sales database and monitor rejected
  audit mutations as security events.
