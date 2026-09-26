#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${CHAOS_DISPOSABLE_ENVIRONMENT:-}" != "yes" ]]; then
  echo "Refusing: set CHAOS_DISPOSABLE_ENVIRONMENT=yes for an isolated stack." >&2
  exit 2
fi

uv run pytest tests/chaos -q

docker compose stop redis
curl --fail --silent http://127.0.0.1:8000/health >/dev/null
docker compose start redis

docker compose stop worker
docker compose start worker
docker compose exec app celery -A vglpos.celery_app call vglpos.reconcile_einvoices >/dev/null

echo "Run the database-disconnect case during a Locust checkout only after confirming the stack is disposable."
echo "Automated injection and recovery assertions passed; record live timing in the incident template."
