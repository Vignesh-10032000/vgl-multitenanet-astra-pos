# Railway demo connection repair

Diagnosis verified on 15 October 2026 in the `happy-connection` project's
production environment:

- The existing PostgreSQL service is running with its persistent volume.
- The Flask service has no app-defined environment variables, so it uses local
  development database and Redis defaults instead of Railway service connections.
- No Redis service is deployed. The runtime logs show Redis connection failures
  before the demo endpoint can seed or authenticate a session.
- `/ready` returns 503 with both database and Redis unavailable.

## Approved repair applied on 15 October 2026

1. Apply the staged, Railway-verified Redis 8.2 template, including its `/data`
   volume and generated Redis password. This adds normal Railway service and
   storage usage. There is no new public Redis domain or TCP proxy in the patch.
2. Add these variables to the existing Flask service:

   | Variable | Value |
   | --- | --- |
   | `APP_ENV` | `production` |
   | `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` |
   | `REDIS_URL` | `${{Redis.REDIS_URL}}` |
   | `DEMO_MODE_ENABLED` | `true` |
   | `PORT` | `8000`, matching the existing Gunicorn listener and public domain |
   | `SECRET_KEY` | Independently generated random value |
   | `JWT_SECRET_KEY` | Independently generated random value |
   | `OFFLINE_SYNC_SIGNING_SECRET` | Independently generated random value |
   | `METRICS_AUTH_TOKEN` | Independently generated random value |

3. Deploy the current Flask application, run the versioned Alembic migrations,
   confirm `/ready` returns 200, and test demo login plus the populated dashboard.

The existing PostgreSQL service, database contents and credentials remain in
place. Secrets are supplied directly to Railway, never committed to GitHub.
The public demo remains an isolated tenant with its existing restricted role.
The preserved `legacy/` application stays inactive.

The user explicitly approved the production changes, including additional Redis
and storage usage. Redis and its persistent volume are now online. The existing
PostgreSQL database was migrated through revision `0017`; it was not replaced.
The app's old source-commit pin was removed, restoring deployment from `main`.

Railway's current connector rejects the legacy `railway.toml` configuration
field. The Dockerfile, `alembic upgrade head` pre-deploy command, `/ready` health
check and 120-second timeouts were therefore configured directly on the service.
`PORT=8000` also aligns Railway's health check with the existing Flask listener.

Production verification for dashboard commit `c8bfdb9` succeeded: `/ready` returns
200 with both dependencies healthy; demo authentication succeeds; the dashboard
contains eight products, five customers, three low-stock alerts, five ranked
products, three payment groups and eight recent sales. GitHub quality and
security checks both passed for this commit. No credentials are recorded here.
