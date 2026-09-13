# VGL POS

GST-compliant retail point of sale for Indian retail (Tamil Nadu first): billing,
inventory, returns, reporting.

- **Stack:** Python 3.12 · Flask 3 (app factory) · SQLAlchemy 2.x · PostgreSQL 16 ·
  Alembic · Redis · Celery · Pydantic v2 · structlog.
- **Layout:** the application lives in `src/vglpos/`. The pre-rewrite prototype is
  preserved untouched in `legacy/` and is not imported by anything under `src/`.
- **Engineering rules:** see [CLAUDE.md](CLAUDE.md). They are enforced in review and CI.

## Quick start

```sh
cp .env.example .env        # fill in values; nothing real is committed
docker compose up -d        # postgres + redis + app + celery worker/beat
make test                   # pytest with coverage
make lint typecheck         # ruff + mypy --strict
make upgrade                # alembic upgrade head
```

Local development without Docker: `uv sync --all-groups`, then `make dev`.

The WSGI entry point is the factory: `gunicorn "vglpos.app:create_app()"`.
No module-level `app` object exists anywhere, by design.
