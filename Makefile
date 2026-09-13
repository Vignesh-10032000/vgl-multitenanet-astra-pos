.PHONY: dev test lint typecheck migrate upgrade downgrade audit

UV ?= uv

dev:
	$(UV) run flask --app vglpos.app run --debug --port 8000

test:
	$(UV) run pytest --cov --cov-fail-under=80

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .

typecheck:
	$(UV) run mypy --strict src/vglpos/services src/vglpos/repositories src/vglpos/utils

# Usage: make migrate m="add sales tables"
migrate:
	$(UV) run alembic revision --autogenerate -m "$(m)"

upgrade:
	$(UV) run alembic upgrade head

downgrade:
	$(UV) run alembic downgrade -1

audit:
	$(UV) export --no-emit-project --format requirements-txt -o .audit-requirements.txt
	$(UV) run pip-audit --disable-pip -r .audit-requirements.txt
