# VGL POS — Standing Engineering Context

## Project
Indian retail POS. Tamil Nadu first. GST-compliant billing, inventory,
returns, reporting. Target: 10,000 users, 10-year lifespan.

## Stack (target)
Python 3.12 · Flask 3 (app factory) · SQLAlchemy 2.x · PostgreSQL 16 ·
Alembic · Redis · Celery · Pydantic v2 · pytest · Jinja2 + vanilla ES modules
+ Alpine.js. SQLite only for the desktop/PyInstaller build.

## Absolute rules — violating any of these fails review
1. ALL money is `decimal.Decimal`. `float` for money is forbidden anywhere,
   including intermediate calculations. Quantities are Decimal with 3 dp.
2. NO business logic in route handlers. Routes parse, delegate to a service,
   serialise. Services never import `flask.request` or `jsonify`.
3. NO raw `db.session` access outside services and repositories.
4. Every query is company-scoped. Repositories take `company_id` in the
   constructor and refuse to run without it.
5. Every API route carries an explicit permission decorator. No exceptions.
   If a route is genuinely public, add it to PUBLIC_ENDPOINTS with a comment
   explaining why.
6. Every schema change is an Alembic migration with a working `downgrade()`.
   `db.create_all()` is forbidden outside tests.
7. Type hints on every function signature. `mypy --strict` on `services/`,
   `repositories/`, `utils/`.
8. Every function that can fail logs with context and raises a typed
   exception. No bare `except:`. No `except Exception: pass`.
9. No TODOs, no placeholders, no pseudo-code, no `...` bodies, no stubs.
   If something cannot be completed, stop and say so explicitly.
10. No secret, hostname, GSTIN, store name, or phone number is hardcoded.
    Config comes from env vars or the database.

## Testing rules
- Every new service method gets unit tests including the failure paths.
- Every bug fixed gets a named regression test referencing the finding ID
  (e.g. `test_p0_3_negative_quantity_rejected`).
- Tests must not touch a real database. The session fixture rolls back.
- Never lower a coverage threshold to make a build pass.

## Style
- Ruff for lint and format. Line length 100.
- Google-style docstrings on every public function, explaining WHY not WHAT.
- Conventional Commits.

## When you are unsure
Stop and ask. Do not guess at a business rule, a tax rule, or a schema
decision. A wrong assumption compounds across the codebase.
