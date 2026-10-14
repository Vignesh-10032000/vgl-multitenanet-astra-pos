# syntax=docker/dockerfile:1

# ---------- web asset stage ----------
FROM node:24-alpine AS web-builder

WORKDIR /app
COPY package.json package-lock.json vite.config.js ./
# Use Docker layer caching without host-specific BuildKit cache-mount IDs.
RUN npm ci
COPY src/vglpos/web/static/src ./src/vglpos/web/static/src
RUN npm run build

# ---------- build stage ----------
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependency layer first so code edits don't bust the dependency cache.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY --from=web-builder /app/src/vglpos/web/static/dist ./src/vglpos/web/static/dist
COPY alembic.ini ./
COPY gunicorn.conf.py ./
COPY migrations ./migrations
RUN uv sync --frozen --no-dev

# ---------- runtime stage ----------
FROM python:3.12-slim AS runtime

RUN groupadd --system vglpos && useradd --system --gid vglpos --create-home vglpos \
    && mkdir -p /tmp/prometheus-multiproc \
    && chown vglpos:vglpos /tmp/prometheus-multiproc

WORKDIR /app
COPY --from=builder --chown=vglpos:vglpos /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus-multiproc

USER vglpos
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"]

CMD ["gunicorn", "--config", "gunicorn.conf.py", "vglpos.app:create_app()"]
