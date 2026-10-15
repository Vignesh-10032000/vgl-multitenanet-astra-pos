# Deployment Security

## Railway service connections

The Flask service requires reachable PostgreSQL and Redis services in the same
Railway project and environment. In the app service's Variables tab, add
reference variables (replace the service names if yours differ):

```text
APP_ENV=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
DEMO_MODE_ENABLED=true
PORT=8000
```

Supply the four independent secrets described below, including
`OFFLINE_SYNC_SIGNING_SECRET` and `METRICS_AUTH_TOKEN`, before deploying.
The app and Alembic accept Railway's `postgresql://` URL and select the installed
Psycopg 3 driver automatically. Never use localhost database URLs in Railway.

Configure `alembic upgrade head` as the pre-deploy command and `/ready` as the
health-check path, with 120-second timeouts. `/ready` checks both PostgreSQL and
Redis. The root `railway.toml` retains these settings for compatible deployments;
the current Railway connector rejects that legacy configuration field, so the
production service has these settings configured directly. `PORT=8000` matches
the current Gunicorn listener and Railway health-check target. The pre-deploy
command requires a schema-owner credential; deployments using separate roles
must instead run migrations in their owner release job before the app deploy.
The `/health` endpoint checks only the web process and does not prove that
login can succeed. A 503 from `/ready` with either dependency unavailable means
the corresponding service connection must be restored. Existing real data and
the Flask runtime must remain on PostgreSQL; do not substitute a demo SQLite
database or bypass Redis session checks to conceal an outage.

After connecting the services, deploy the latest commit and confirm `/ready`
returns 200, then test the demo button. Dependency outages return a retryable
503 with a support reference rather than leaking connection credentials.

References: [Railway PostgreSQL](https://docs.railway.com/databases/postgresql),
[Redis](https://docs.railway.com/databases/redis), and
[config as code](https://docs.railway.com/config-as-code/reference).

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
