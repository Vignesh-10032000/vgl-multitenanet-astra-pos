# Developer onboarding

## Prerequisites

Install Python 3.12, uv, Node.js 24, Docker with Compose, Git and PostgreSQL client tools. On Windows, run application commands in PowerShell and backup scripts in WSL or CI Linux.

## First run

1. Copy `.env.example` to `.env` and replace every development value locally. Never commit `.env`.
2. Start PostgreSQL and Redis: `docker compose up -d postgres redis`.
3. Install pinned dependencies: `uv sync --all-groups` and `npm ci`.
4. Run migrations explicitly: `uv run alembic upgrade head`.
5. Seed reference data: `uv run flask --app vglpos.app seed-reference`.
6. Build assets: `npm run build`.
7. Start the API: `uv run flask --app vglpos.app run --port 8000`.
8. Open `http://127.0.0.1:8000/login`; check `/health` and `/ready`.

## Change workflow

Keep HTTP parsing in API routes, business transactions in services, tenant-filtered reads in repositories, and persistence facts in typed models/migrations. Every mutation needs a permission, idempotency decision, audit decision and test. Never trust browser price, tax, scope or totals.

Before review run:

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src/vglpos/services src/vglpos/repositories src/vglpos/utils
uv run pytest --cov --cov-fail-under=80
npm run build
npm test
npm audit --audit-level=high
```

Use a disposable database ending in `_test` for PostgreSQL tests. Never point pytest at development or production. Migrations must upgrade, downgrade one revision, and re-upgrade. Regenerate UI screenshots only from seeded synthetic data.

## Operations development

Run Prometheus/Grafana with the base compose file plus `ops/docker-compose.observability.yml`, supplying token/password files outside Git. See `docs/runbook.md` before backup, restore, chaos, deployment or rollback work. Feature flags are `einvoice`, `eway_bill`, and `report_jobs`.
