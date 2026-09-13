# VGL POS — Phased Rebuild Prompt Pack

**Purpose:** a paste-ready sequence of prompts that takes the current `POS-project-main` prototype to a production-grade system, with a verifiable gate at the end of every phase.

**Read this section before you paste anything.**

---

## 0. How to use this pack

### 0.1 What "100 percent" actually means here

There is no prompt that returns a finished, correct enterprise system in one shot. What this pack gives you is a definition of done that can be *checked by a machine*, and a sequence that reaches it:

| Definition of done | How it is proven |
|---|---|
| Every P0 and P1 from the audit is closed | A named regression test per finding, listed in each phase gate |
| Money arithmetic is exact | 100% branch coverage on `money.py` and `tax_engine.py`, property-based tests |
| No unguarded endpoint exists | A test that enumerates `app.url_map` and fails the build on any gap |
| Invoices reconcile | DB `CHECK` constraint + service assertion + parametrised test |
| Concurrency is safe | Threaded test that races two checkouts for the last unit |
| Performance targets met | Locust run in CI with p99 thresholds |
| Deploys are reversible | Every Alembic migration has a tested `downgrade()` |
| Backups work | A restore drill that runs in CI against a scratch database |

If all eight hold, you are done in every sense that can be verified. What no agent can verify for you is whether the business rules match how *your* shop actually operates. That is what the human review gate at each phase boundary is for.

### 0.2 Tooling

Use an agentic coding tool with filesystem and terminal access, not a chat window — these phases span many files and need to run tests between edits. Work in a git repo, one branch per phase.

### 0.3 Non-negotiable rules for every session

Paste these with every prompt, or better, put them in a `CLAUDE.md` at the repo root so they load automatically:

```markdown
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
```

### 0.4 Phase discipline

For each phase, in order:

1. `git checkout -b phase-N-<name>`
2. Paste the phase prompt.
3. Let the agent work. Interrupt if it drifts from scope.
4. Run the phase's **gate commands** yourself. Do not take the agent's word.
5. **Read the diff.** Especially anything touching money, tax, stock, or auth.
6. Merge. Tag. Move on.

Never start phase N+1 with phase N's gate failing. Debt compounds faster than features.

### 0.5 Phase map

| Phase | Name | Effort | Ships? |
|---|---|---|---|
| 0 | Emergency hotfix | 4–8 hours | Yes — deploy immediately |
| 1A | Scaffold, config, infra | 2–3 days | No |
| 1B | Domain models & migrations | 3–4 days | No |
| 1C | Money & tax engine | 3–4 days | No |
| 1D | Services & repositories | 4–5 days | No |
| 1E | Data migration from prototype | 2 days | No |
| 2 | Identity, RBAC, audit | 5–7 days | No |
| 3 | API v1 | 5–7 days | Internal alpha |
| 4 | Performance | 3–4 days | Internal alpha |
| 5 | Front-end rebuild | 7–10 days | **Yes — pilot store** |
| 6 | Offline PWA | 5–7 days | Yes |
| 7 | Retail operations | 7–10 days | Yes |
| 8 | Business depth | 10–14 days | Yes |
| 9 | E-invoicing & compliance | 7–10 days | Yes |
| 10 | Hardening & operations | 5–7 days | **Production GA** |

Total ≈ 14–18 weeks of focused work.

---

## PHASE 0 — Emergency hotfix

**Goal:** close every remotely-exploitable hole in the *existing* codebase without restructuring anything. This ships today. Do not refactor.

```
ROLE: Senior Python/Flask security engineer.

CONTEXT
I have a Flask POS application (the current working tree). It is a prototype
that has been deployed publicly. A security audit found live, remotely
exploitable defects. Your job is to close them with the MINIMUM possible
change. Do NOT restructure, do NOT introduce new dependencies, do NOT
refactor. Every change must be surgical and independently reviewable.

FINDINGS TO FIX — each needs a code fix AND a regression test named after it.

[P0-1] app.py exposes `POST /api/demo/reset` which calls db.drop_all() with
no authentication. Also `POST /api/demo/simulate_sale`.
FIX: Gate both behind an environment check. They may only be registered when
os.environ.get('APP_ENV') == 'demo' AND a valid X-Demo-Token header matching
os.environ['DEMO_TOKEN'] is present. In any other environment the routes must
not exist at all (return 404, not 403 — do not advertise them).

[P0-3] routes/pos.py checkout() accepts negative and zero quantities. A POST
with quantity -5 returns 200, INCREASES stock, and returns a positive
change_given, instructing the cashier to pay out cash. Unbounded `discount`
likewise produces negative sale totals.
FIX: Validate before any mutation:
  - quantity must be an integer > 0 and <= 10000 per line
  - number of lines must be 1..200
  - discount must be >= 0 and <= the pre-discount cart total
  - amount_paid must be >= 0
  - customer_id, if supplied, must exist
Return HTTP 400 with a clear message for each. Reject the whole request; do
not silently clamp values.

[P0-4] checkout() computes CGST/SGST on the pre-discount value but stores
`total` post-discount, so the invoice does not reconcile. Verified: a ₹299
item at 18% with ₹50 discount stores taxable 253.39 + CGST 22.80 +
SGST 22.80 = 298.99 against a total of 249.00.
FIX: Apportion the order discount across lines by their gross value BEFORE
computing tax, then compute tax on the post-discount line value. Use the
largest-remainder method so the apportioned parts sum EXACTLY to the discount
with no lost paisa. Assert before commit that
taxable + cgst + sgst == total (tolerance 0.01) and raise if not.
Use decimal.Decimal for this calculation even though the columns are still
Float — convert to float only at the moment of assignment.

[P0-6] test_app.py overrides SQLALCHEMY_DATABASE_URI AFTER create_app(), but
Flask-SQLAlchemy 3.x builds engines inside init_app(). The override has no
effect, so setUp seeds and tearDown drop_all()s the REAL instance/pos.db.
FIX: Change create_app() to accept an optional config dict/object applied
BEFORE db.init_app(). Update test_app.py to pass a test config with
sqlite:///:memory:. Add an assertion in setUp that fails loudly if
db.engine.url does not contain ':memory:'.

[P0-8] templates/*.html build DOM with innerHTML from unescaped server data.
The helper named escHtml() only escapes apostrophes:
  function escHtml(s) { return s.replace(/'/g, "\\'"); }
A product named `<img src=x onerror=...>` executes on every POS screen.
FIX: Add a single correct escapeHtml() to static/js/pos.js escaping
& < > " ' and apply it to EVERY interpolation of server-supplied data in
every template. Rename the existing misleading escHtml to escJsString and
keep it only where a JS string literal is genuinely being built. Audit all
9 templates; do not stop at pos.html.

[P3-1] templates/pos.html parses the cart total out of the DOM:
  parseFloat(el.textContent.replace('₹','').replace(',',''))
.replace(',','') replaces only the FIRST comma. With Indian digit grouping
"₹1,00,000.00" parses as 100.00, defeating the cash-tendered check.
FIX: Keep the cart total as a JavaScript Number in module state and use that
value directly. Never round-trip money through the DOM. Verify with test
values 1234.00, 100000.00, 1234567.89.

[P1-8] The global error handler returns str(e) to the client, leaking SQL and
schema details.
FIX: Log the full traceback server-side with a uuid4 request id; return only
{"error": "Internal server error", "request_id": "<uuid>"} to the client.

[P1-10] CORS(app) allows every origin on an API with no authentication.
FIX: Restrict to origins from a CORS_ORIGINS env var (comma-separated).
Default to same-origin only (empty list).

[P1-11] SECRET_KEY falls back to the hardcoded literal 'tn-pos-secret-2024'.
FIX: If APP_ENV is 'production' and SECRET_KEY is unset, raise RuntimeError
at startup and refuse to boot. Keep a random per-process fallback for dev.

ALSO
- Add a DELETE guard: `DELETE /api/sales/<id>` currently hard-deletes a
  financial record. Change it to set a new `cancelled_at` column
  (add via a plain ALTER in a small standalone script, documented) and stop
  deleting. Stock restoration stays.
- Remove the committed ngrok.yml and the loaderio token file from the repo,
  and add them to .gitignore.
- Remove the hardcoded BASE_URL in routes/sales.py; read it from an env var.

CONSTRAINTS
- No new dependencies.
- No file moves or renames beyond what is listed.
- Every fix independently revertable.
- Keep every existing endpoint working for the current front-end.

DELIVERABLES
1. The code changes.
2. A rewritten test_app.py with true in-memory isolation plus one regression
   test per finding above, named test_p0_1_*, test_p0_3_*, etc.
3. HOTFIX_NOTES.md listing each finding, the fix, the file(s) touched, and
   the exact command to verify it.

GATE — I will run these and they must all pass:
  pytest -v
  APP_ENV=production python -c "import app"   # must raise on missing SECRET_KEY
  curl -X POST localhost:5000/api/demo/reset  # must 404
  curl -X POST localhost:5000/api/checkout -H 'Content-Type: application/json' \
    -d '{"items":[{"product_id":1,"quantity":-5}],"amount_paid":0}'   # must 400
  curl -X POST localhost:5000/api/checkout -H 'Content-Type: application/json' \
    -d '{"items":[{"product_id":1,"quantity":1}],"discount":99999}'   # must 400

Work through the findings in order. After each one, run the tests before
moving to the next. Report which findings are fixed as you go.
```

**Human review checklist for Phase 0:** confirm the demo routes are absent from a production boot (`flask routes | grep demo` returns nothing); manually POST a negative quantity and a huge discount against your staging deploy; view a product named `<img src=x onerror=alert(1)>` on every screen.

---

## PHASE 1A — Scaffold, config, infrastructure

**Goal:** create the target project skeleton, running side by side with the prototype. Nothing is migrated yet.

```
ROLE: Senior software architect, Python/Flask.

CONTEXT
I am rebuilding a Flask POS application on a clean layered architecture.
The existing prototype is in ./legacy/ (move it there first). The new
application lives in ./src/vglpos/. This phase creates the skeleton and
infrastructure only — no domain logic yet.

TASK
Create the following, complete and runnable:

1. pyproject.toml (uv or poetry) with pinned dependencies and a lockfile:
   flask, flask-sqlalchemy, flask-migrate, flask-jwt-extended, flask-limiter,
   flask-caching, psycopg[binary], alembic, pydantic, pydantic-settings,
   celery, redis, argon2-cffi, gunicorn, structlog, python-dateutil.
   Dev group: pytest, pytest-cov, pytest-postgresql, hypothesis, factory-boy,
   ruff, mypy, pip-audit, locust, playwright.

2. src/vglpos/config.py — Pydantic Settings classes:
   BaseConfig, DevelopmentConfig, TestingConfig, ProductionConfig.
   ProductionConfig MUST raise at construction if SECRET_KEY, JWT_SECRET_KEY,
   or DATABASE_URL is missing or is a known-default value. Include
   SQLALCHEMY_ENGINE_OPTIONS with pool_size=10, max_overflow=20,
   pool_pre_ping=True, pool_recycle=1800.

3. src/vglpos/extensions.py — db, migrate, cache, limiter, jwt, celery
   instances, uninitialised.

4. src/vglpos/app.py — create_app(config_class) with:
   - config applied BEFORE any extension init (this is the P0-6 bug class)
   - extensions initialised
   - blueprints registered from a registry list
   - request_id middleware (uuid4 into flask.g and the X-Request-Id header)
   - structlog JSON logging bound with request_id, user_id, company_id
   - RFC 7807 error handlers
   - security headers WITHOUT 'unsafe-inline' in script-src
   - NO db.create_all(), NO seeding, NO side effects at import time
   - a module-level `app` object must NOT exist; entry points call the factory

5. Alembic wired to the app factory; alembic.ini; env.py that reads
   DATABASE_URL from config. Generate an empty initial revision.

6. docker-compose.yml: postgres:16-alpine with healthcheck, redis:7-alpine,
   app (gunicorn), worker (celery), beat. Named volume for pgdata.

7. Dockerfile: multi-stage, non-root user, healthcheck.

8. .env.example with every variable documented and NO real values.
   .gitignore covering .env, *.db, instance/, __pycache__, .venv, dist/.

9. Makefile: make dev, make test, make lint, make typecheck, make migrate,
   make upgrade, make downgrade, make audit.

10. tests/conftest.py with:
    - session-scoped `app` fixture passing TestingConfig INTO create_app
    - function-scoped `db_session` fixture using a connection-level
      transaction with a SAVEPOINT that is rolled back after every test
    - a `client` fixture
    - an autouse fixture that ASSERTS the engine URL is the test database
      and errors loudly otherwise

11. .github/workflows/ci.yml running: ruff check, ruff format --check,
    mypy --strict src/vglpos/{services,repositories,utils}, pytest with
    --cov and --cov-fail-under=80, pip-audit.

12. CLAUDE.md at the repo root containing the standing engineering rules
    (I will provide the text; create the file and I will paste them in).

CONSTRAINTS
- No domain models in this phase. No routes beyond /health.
- The app must boot, /health must return 200, and the test suite must run
  green with zero tests.

GATE
  docker compose up -d && sleep 10
  make test          # green, 0 failures
  make lint          # clean
  make typecheck     # clean
  curl localhost:8000/health   # 200
  alembic upgrade head && alembic downgrade base && alembic upgrade head
  APP_ENV=production python -c "from vglpos.config import ProductionConfig; ProductionConfig()"
    # must raise on missing secrets
```

---

## PHASE 1B — Domain models and migrations

**Goal:** the full schema, as Alembic migrations with working rollbacks.

```
ROLE: Senior database architect, PostgreSQL + SQLAlchemy 2.x.

CONTEXT
The scaffold from Phase 1A is in place. Now build the complete domain model
for an Indian retail POS: multi-company, multi-branch, multi-terminal, GST
compliant, with a full audit trail.

I am attaching the target DDL (see VGL_POS_Architecture_Review.md §5.2).
Implement it as SQLAlchemy 2.x declarative models plus Alembic migrations.
Follow the DDL exactly for column types, constraints and indexes. Where you
disagree with a design decision, implement it as specified and raise the
concern in a separate DESIGN_NOTES.md — do not silently deviate.

TABLES, in migration order:
  001_core_tenancy      companies, branches, terminals
  002_identity          users, roles, permissions, role_permissions, user_roles
  003_tax_catalogue     tax_rates, hsn_codes, categories, products,
                        product_barcodes, product_price_history
  004_parties           customers, suppliers
  005_documents         document_series, sales, sale_items, sale_payments,
                        credit_notes, credit_note_items
  006_inventory         stock_ledger, stock_batches, purchases, purchase_items
  007_shifts_audit      shifts, cash_movements, audit_log (partitioned),
                        mv_daily_sales_summary

MANDATORY across every table:
- BIGINT surrogate primary keys.
- Audit columns: created_at, created_by, updated_at, updated_by,
  deleted_at, deleted_by, row_version. Implement as a declarative mixin.
- Soft delete via partial unique indexes: WHERE deleted_at IS NULL.
- ALL money columns NUMERIC(14,2). ALL quantity columns NUMERIC(12,3).
  There must be ZERO Float columns. Verify this with a test that introspects
  the metadata and fails on any Float.
- Every FK has an explicit ON DELETE policy (RESTRICT by default; CASCADE
  only for child rows of an aggregate root such as sale_items).
- Every CHECK constraint from the DDL, especially:
    ck_sales_reconcile  — taxable+cgst+sgst+igst+cess+round_off == net_amount
    ck_sale_items_qty   — quantity > 0
    ck_sales_tax_mode   — interstate XOR intrastate tax populated

ALSO BUILD
- src/vglpos/domain/enums.py: PaymentMethod, SaleStatus, SupplyType,
  LedgerTxnType, ShiftStatus, DocType, ReturnReason. Use StrEnum.
- A `TenantMixin` providing company_id + the FK, applied to every tenant table.
- Model-level __repr__ that never prints monetary values or PII.
- src/vglpos/domain/events.py: dataclasses for SaleCompleted, StockDepleted,
  ShiftClosed, PriceOverridden. No dispatcher yet, just the types.
- A seed script (src/vglpos/cli/seed_reference.py, a Flask CLI command)
  loading: the 37 Indian state codes, the GST 2.0 rate slabs
  (0 / 5 / 18 / 40, effective_from 2025-09-22) AND the pre-2.0 slabs
  (0 / 5 / 12 / 18 / 28, effective_from 2017-07-01, effective_to 2025-09-21)
  so historical invoices reprint correctly, and the standard permission rows.

CONSTRAINTS
- Every migration must have a working downgrade(). Test it.
- Use CREATE INDEX CONCURRENTLY for indexes on tables expected to be large,
  with the migration marked as non-transactional.
- No business logic in models. Models are data + constraints only. Properties
  that compute derived values are forbidden — that logic belongs in services.

DELIVERABLES
1. Models under src/vglpos/domain/models/, one module per aggregate.
2. Seven Alembic migrations with tested downgrades.
3. tests/unit/test_schema.py asserting: no Float columns anywhere; every
   table has the audit columns; every FK has an ondelete; every money column
   is NUMERIC(14,2).
4. DESIGN_NOTES.md for any concerns.
5. An ERD (mermaid) in docs/erd.md.

GATE
  alembic upgrade head
  alembic downgrade base
  alembic upgrade head              # all three must succeed
  pytest tests/unit/test_schema.py -v
  flask seed-reference              # loads states, rates, permissions
  psql -c "\d+ sales"               # verify constraints exist
  # This INSERT must be REJECTED by ck_sales_reconcile:
  psql -c "INSERT INTO sales (...) VALUES (... taxable 253.39, cgst 22.80,
           sgst 22.80, net 249.00 ...)"
```

---

## PHASE 1C — Money and tax engine

**Goal:** the most-tested code in the repository. Everything downstream depends on this being exactly right.

```
ROLE: Senior engineer specialising in financial software correctness.

CONTEXT
Building the monetary and GST calculation core for an Indian retail POS.
This code is the single source of truth for all tax arithmetic. The prototype
it replaces had a reconciliation bug that made every discounted invoice
legally invalid. Correctness here matters more than anything else in the
system.

TASK 1 — src/vglpos/utils/money.py
Implement, with full docstrings and doctests:
  to_decimal(value)          coerce without routing through binary float
                             (floats must be stringified first — Decimal(0.1)
                             is not 0.1)
  money(value)               quantize to 2dp, ROUND_HALF_UP (NOT banker's
                             rounding — Indian retail rounds half up)
  qty(value)                 quantize to 3dp
  round_off_to_rupee(value)  -> (rounded_total, delta) for Indian invoice
                             round-off
  apportion(total, weights)  split a total across weights so the parts sum
                             EXACTLY to the total. Largest-remainder method.
                             This is the function whose absence caused the
                             production bug.
  inr_in_words(amount)       "Seven Hundred Thirteen Rupees Only" — Indian
                             system (lakh, crore), required on invoices
  format_inr(amount)         ₹1,00,000.00 Indian digit grouping

TASK 2 — src/vglpos/utils/gst.py
  validate_gstin(gstin)      regex + state code validity + CHECK DIGIT
                             (the mod-36 algorithm — regex alone accepts
                             typos the IRP will reject)
  state_code_from_gstin(g)   first two digits
  STATE_CODES                dict of all 37 codes to names
  financial_year_code(date)  Indian FY, 1 Apr–31 Mar, '26-27' format
  is_interstate(supplier_state, place_of_supply)

TASK 3 — src/vglpos/services/tax_engine.py
A PURE, stateless class. No database. No Flask. No I/O. No global state.

  TaxEngine.compute(
      lines: list[TaxLineInput],
      *, supplier_state: str, place_of_supply: str,
      order_discount: Decimal = ZERO,
      apply_round_off: bool = True,
  ) -> TaxResult

Algorithm, in this exact order:
  1. Validate every line: quantity > 0, unit_price >= 0, 0 <= tax_rate <= 100,
     line_discount <= line gross. Raise ValueError with a specific message.
  2. Compute per-line gross, minus any line-level discount.
  3. Apportion the ORDER-level discount across lines by gross value, using
     apportion(). The parts must sum exactly to the discount.
  4. For each line, compute tax on the POST-discount value. If the price is
     tax-inclusive, extract: taxable = net / (1 + (rate + cess) / 100).
  5. Interstate -> IGST only. Intrastate -> CGST = tax // 2,
     SGST = tax - CGST, so the halves always re-add to the whole with no
     lost paisa on odd amounts.
  6. Roll up; apply invoice round-off to the nearest rupee; record the delta.
  7. assert_reconciles() — taxable + cgst + sgst + igst + cess + round_off
     must equal net_amount within 0.01, else raise.

TASK 4 — tests. This is the deliverable I will scrutinise most.
tests/unit/test_money.py and tests/unit/test_tax_engine.py must achieve
100% BRANCH coverage on both modules and must include:

  Reconciliation (regression for P0-4):
    - parametrised over discounts: 0, 0.01, 50.00, and exactly the full
      order value
    - mixed-rate carts (5% + 18% + 40% lines) with an order discount:
      assert the apportioned discounts sum EXACTLY to the input discount
    - assert cgst + sgst == total tax exactly, for tax amounts that are odd
      in paise (e.g. taxable 333.33 at 5%)

  Rejections (regression for P0-3):
    - quantity of -5, 0, and a non-numeric value
    - discount exceeding the order value
    - tax rate of -1 and 101

  Interstate (regression for P1-2):
    - supplier 33, place of supply 29 -> IGST > 0, CGST == SGST == 0
    - supplier 33, place of supply 33 -> IGST == 0, CGST > 0, SGST > 0

  Rate history (regression for P1-3):
    - a product on the 12% slab billed on 2025-09-20 uses 12%
    - the same product billed on 2025-09-25 uses its post-GST-2.0 rate

  Property-based (hypothesis), minimum 1000 examples each:
    - for any cart of 1..50 lines with any rates from {0,5,18,40} and any
      discount from 0 to the order total: the result ALWAYS reconciles
    - apportion(total, weights) ALWAYS sums to exactly total
    - money(x) is idempotent: money(money(x)) == money(x)

  Golden-file tests:
    - a fixture file of 20 real-world invoice scenarios with hand-calculated
      expected outputs, verified by hand against a GST calculator. Include
      the exact case from the audit:
      1 x Rs.299 at 18% inclusive, order discount Rs.50, intra-state TN
      -> gross 299.00, discount 50.00, taxable 211.02, cgst 18.99,
         sgst 18.99, round_off 0.00, net 249.00

CONSTRAINTS
- Zero float. A test must introspect the module and fail if `float(` appears
  in any non-test source file under utils/ or services/tax_engine.py.
- TaxEngine must be importable and fully usable with no Flask app context.

GATE
  pytest tests/unit/test_money.py tests/unit/test_tax_engine.py \
    --cov=vglpos.utils.money --cov=vglpos.utils.gst \
    --cov=vglpos.services.tax_engine --cov-branch --cov-fail-under=100
  mypy --strict src/vglpos/utils src/vglpos/services/tax_engine.py
  python -c "from vglpos.services.tax_engine import TaxEngine"  # no Flask needed
  grep -rn "float(" src/vglpos/utils src/vglpos/services/tax_engine.py  # empty
```

**Do not skip the golden-file tests.** Hand-calculate all 20 yourself against an independent GST calculator. If the agent generates both the code and the expected values, the test proves nothing.

---

## PHASE 1D — Repositories and services

```
ROLE: Senior software architect, domain-driven design in Python.

CONTEXT
Models (1B) and the tax engine (1C) exist. Now build the layer between HTTP
and the database. Routes do not exist yet and must not be created in this
phase — services are tested directly.

TASK 1 — src/vglpos/repositories/
  base.py: BaseRepository[T] generic, constructor takes company_id and RAISES
  ValueError if it is falsy. _base_query() always filters company_id and
  deleted_at IS NULL. Methods: get, get_or_raise, list (CURSOR paginated,
  not offset), add, soft_delete, count.
  Then: ProductRepository (incl. find_by_barcode with a single indexed
  lookup, search with trigram), CustomerRepository, SaleRepository,
  StockRepository, UserRepository, ShiftRepository.

TASK 2 — src/vglpos/services/
  invoice_number_service.py
    allocate(company_id, branch_id, terminal_id, doc_type, on_date)
    -> (document_no, fy_code). Uses SELECT ... FOR UPDATE on document_series.
    MUST run inside the caller's transaction so a rollback does not burn a
    number and create a gap in the series (GST Rule 46(b) requires
    consecutive numbering). Raise if the result exceeds 16 characters.

  inventory_service.py
    record_movement(product, branch_id, quantity_delta, txn_type, ref_table,
                    ref_id, user_id, batch_id=None, unit_cost=None)
    Appends to stock_ledger AND updates products.on_hand atomically using a
    SQL-side expression (Product.on_hand + delta), never a Python-computed
    value. This is the ONLY code in the system permitted to change on_hand;
    add a test that greps for other assignments.
    Also: reserve_stock, release_reservation, adjust_stock (reason required),
    weighted_average_cost_update.

  checkout_service.py
    checkout(cmd: CheckoutCommand) -> Sale
    Guarantees, each with a test:
      a) idempotent on cmd.offline_uuid — a replay returns the ORIGINAL sale
      b) product rows locked with SELECT ... FOR UPDATE, ORDERED BY id to
         prevent deadlock between two terminals
      c) quantities aggregated per product before the stock check (a cart may
         contain the same product on two lines)
      d) stock never goes negative unless the product allows it
      e) place of supply resolved from the customer GSTIN state code;
         interstate -> IGST
      f) tax computed SERVER-SIDE ONLY. Any client-supplied total is ignored.
      g) tendered amount >= payable; change <= cash tendered specifically
         (you cannot give change against a card payment)
      h) invoice number allocated inside the same transaction
      i) loyalty points and customer counters updated
      j) a single commit; IntegrityError rolls back and raises a typed error

  return_service.py
    create_credit_note(...) — validates against ALL prior returns for the
    sale, computes the tax breakup using the ORIGINAL invoice's tax rate (not
    today's rate), reverses loyalty points, restocks via inventory_service,
    allocates a CREDIT_NOTE document number.

  shift_service.py    open_shift, close_shift (blind count -> variance),
                      record_cash_movement, z_report
  report_service.py   daily_summary, revenue_series (ONE GROUP BY query, not
                      a loop), top_products, payment_mix, gstr1_data

TASK 3 — typed exceptions in src/vglpos/services/exceptions.py, each with a
status_code and an error_type slug for RFC 7807.

TASK 4 — tests/integration/ for every service, including:
  test_p0_7_concurrent_checkout_cannot_oversell — two threads, a
    threading.Barrier to force simultaneity, one must succeed and one must
    raise InsufficientStockError, and on_hand must end at exactly 0
  test_invoice_numbers_have_no_gaps — 100 sequential checkouts, 10 of which
    are forced to roll back; assert the committed numbers are consecutive
  test_idempotent_replay_returns_original_sale
  test_return_uses_original_invoice_tax_rate
  test_repository_refuses_to_run_without_company_id

CONSTRAINTS
- No service imports flask.request, flask.g, or jsonify.
- Services receive a Command dataclass, return a domain object or a DTO.
- Every service method has a docstring stating its transactional guarantees.

GATE
  pytest tests/integration -v
  pytest tests/integration/test_concurrency.py -v --count=20   # flakiness check
  mypy --strict src/vglpos/services src/vglpos/repositories
  grep -rn "on_hand =" src/vglpos --include=*.py | grep -v inventory_service
    # must be empty
  grep -rn "from flask import" src/vglpos/services   # must be empty
```

---

## PHASE 1E — Data migration from the prototype

```
ROLE: Senior data engineer.

CONTEXT
I have production data in the legacy prototype's SQLite database
(legacy/instance/pos.db) using the old schema with Float money columns and
no company/branch/user concept. Migrate it into the new PostgreSQL schema
without losing or corrupting a single rupee.

TASK
Write scripts/migrate_legacy.py, a Flask CLI command, that:

1. PRE-FLIGHT: dump the legacy DB to a timestamped backup file first. Refuse
   to run if the target database has any rows in `sales`.

2. Creates the tenant scaffolding: one Company (details read from a config
   file, NOT hardcoded), one Branch, one Terminal, and a system User named
   'legacy-import' to satisfy created_by.

3. Migrates in dependency order: categories -> products (with barcodes
   extracted into product_barcodes) -> customers -> sales -> sale_items ->
   sale_returns -> credit_notes.

4. MONEY CONVERSION — the critical step. Every Float becomes Decimal via
   str() to avoid binary artefacts. After each table, run a verification
   query comparing SUM() before and after, to 2 decimal places. Abort and
   roll back the whole migration on ANY mismatch.

5. INVOICE NUMBERS: the legacy schema used the raw PK. Generate a synthetic
   series 'LEGACY/<fy>/000001'... ordered by created_at, and record the
   mapping in a legacy_id_map table so old receipt links keep working.

6. TIMESTAMPS: legacy rows used naive datetime.utcnow(). Convert to
   timezone-aware UTC, then derive business_date in Asia/Kolkata honouring
   the configured day-close hour. Report how many rows change business day
   as a result (they will — the UTC day rolls at 05:30 IST).

7. TAX RECONCILIATION: legacy sales with a discount do NOT reconcile
   (the P0-4 bug). For each, RECOMPUTE the tax breakup with TaxEngine using
   the stored line data, and write both the original and corrected values to
   a reconciliation report. Do NOT silently overwrite — produce
   MIGRATION_TAX_CORRECTIONS.csv for your accountant to review, and apply
   corrections only when run with --apply-tax-corrections.

8. OPENING STOCK: create a stock_ledger OPENING row per product from the
   legacy `stock` value, so the ledger balances to on_hand from day one.

9. Emits MIGRATION_REPORT.md: row counts in and out, sum checks per table,
   business-day shifts, tax corrections, and anything skipped with reasons.

CONSTRAINTS
- Idempotent: safe to run twice (second run detects and aborts).
- Single transaction; all or nothing.
- Never invent data. If a required field is missing, record it in the report
  and use a documented default; never guess.

GATE
  flask migrate-legacy --dry-run     # report only, no writes
  flask migrate-legacy
  # Verify by hand:
  psql -c "SELECT SUM(net_amount) FROM sales"
  sqlite3 legacy/instance/pos.db "SELECT SUM(total) FROM sales"
    # must match to 2dp
  psql -c "SELECT COUNT(*) FROM sales WHERE
           ABS((taxable_amount+cgst_amount+sgst_amount+igst_amount+
                cess_amount+round_off) - net_amount) > 0.02"
    # must be 0
```

---

## PHASE 2 — Identity, RBAC, audit trail

```
ROLE: Senior application security engineer.

CONTEXT
The prototype had NO authentication of any kind — every endpoint, including
database deletion, was world-writable. Build the identity layer. Models exist
from Phase 1B (users, roles, permissions, role_permissions, user_roles,
audit_log).

TASK 1 — Authentication (src/vglpos/security/)
  password.py: Argon2id via argon2-cffi, time_cost=3, memory_cost=65536,
    parallelism=4. hash_password, verify_password, needs_rehash.
    A separate hash_pin/verify_pin for the 4-6 digit counter PIN, with a
    lower work factor (it is used many times per shift) but rate limited
    much harder.
  auth_service.py:
    authenticate(username, password) and authenticate_pin(user_id, pin)
    - constant-time comparison
    - progressive lockout: 5 failures -> locked_until = now + 15 min,
      doubling on repeat, recorded on the user row
    - the SAME response time and message for unknown user and wrong password
      (no user enumeration)
    - on success: reset failed_attempts, set last_login_at, write an audit
      row, issue tokens
  tokens: flask-jwt-extended. Access token 15 min carrying
    {sub, company_id, branch_id, terminal_id, permissions[], jti}.
    Refresh token 7 days, ROTATED on every use, old jti added to a Redis
    denylist. Logout revokes.

TASK 2 — Authorization
  decorators.py: @require_permission(*codes, require_all=False)
    - verifies the JWT
    - checks permissions from the token claims
    - sets g.company_id, g.branch_id, g.user_id from the TOKEN ONLY, never
      from the request body (this is the multi-tenancy boundary)
    - logs denials with user, path and the permission required
    - marks the wrapped function with _permission_required = True so the
      coverage test can find it
  Permission codes, seeded: sale.create, sale.view, sale.void,
    sale.discount, sale.price_override, product.view, product.create,
    product.edit, product.delete, stock.adjust, stock.view,
    customer.view, customer.create, customer.edit, customer.export,
    return.create, return.approve, report.view, report.gst, report.export,
    shift.open, shift.close, cash.move, user.manage, settings.manage,
    einvoice.generate, purchase.create, purchase.approve
  Standard roles, seeded: OWNER (all), MANAGER (all except user.manage and
    settings.manage), CASHIER (sale.create, sale.view own, return.create,
    shift.*, cash.move, customer.view/create), STOCK_CLERK, ACCOUNTANT
    (reports + exports, no sale creation), AUDITOR (read-only everything).

TASK 3 — Discount and override limits
  Roles carry max_discount_percent. A discount above the cashier's limit
  requires a manager PIN supplied in the same request
  (approval_pin + approver_user_id), verified server-side, and recorded in
  audit_log with the reason. Same mechanism for price overrides and voids.

TASK 4 — Audit trail
  audit.py: a SQLAlchemy after_flush listener that writes to audit_log for
  every INSERT/UPDATE/DELETE on a configured set of models, capturing
  old_values and new_values as JSONB diffs (changed fields only), plus
  user_id, ip, user_agent, request_id.
  - Never log password_hash, pin_hash, or mfa_secret. Redact them.
  - The audit_log table must be append-only: create a DB role for the app
    that has INSERT but not UPDATE or DELETE on it, and document this in the
    deployment notes.
  - Explicit audit events for: LOGIN_SUCCESS, LOGIN_FAILURE, LOGOUT,
    PERMISSION_DENIED, SALE_VOID, PRICE_OVERRIDE, DISCOUNT_OVERRIDE,
    STOCK_ADJUST, SHIFT_CLOSE_VARIANCE, EXPORT.

TASK 5 — Session hardening
  - Idle timeout: 30 min cashier, 10 min for roles holding user.manage.
  - Screen-lock endpoint that keeps the shift open but requires a PIN to
    resume (a cashier stepping away must not have to close their till).
  - Optional TOTP MFA for OWNER and roles with user.manage.

TASK 6 — Tests
  tests/integration/test_auth.py and test_authorization.py, including:
    test_p0_2_every_api_route_is_permission_guarded
      — enumerate app.url_map, assert every /api/ rule's view function has
        _permission_required, except an explicit PUBLIC_ENDPOINTS allowlist.
        THIS TEST MUST FAIL THE BUILD, not warn.
    test_token_cannot_be_used_to_access_another_company
      — user of company A requests an entity of company B -> 404 (not 403;
        do not confirm the entity exists)
    test_lockout_after_five_failures
    test_refresh_token_rotation_invalidates_the_old_token
    test_unknown_user_and_wrong_password_are_indistinguishable
      — assert both message and response time within tolerance
    test_audit_log_records_who_changed_what
    test_audit_log_redacts_password_hash
    test_discount_above_role_limit_requires_manager_pin

CONSTRAINTS
- No permission logic anywhere except the decorator and the service layer.
- company_id is NEVER read from a request body or query string.
- Fail closed everywhere: an unknown permission code raises at startup.

GATE
  pytest tests/integration/test_auth.py tests/integration/test_authorization.py -v
  pytest -k "test_p0_2_every_api_route_is_permission_guarded" -v
  # Manual: obtain a token for company A, request /api/v1/products/<id of
  # company B> -> must be 404
```

---

## PHASE 3 — API v1

```
ROLE: Senior API designer, Flask + Pydantic v2.

CONTEXT
Services (1D) and auth (2) exist. Build the HTTP layer. Routes are thin:
parse -> authorise -> delegate -> serialise. No business logic.

TASK 1 — DTOs in src/vglpos/api/v1/schemas/ using Pydantic v2
  - model_config = ConfigDict(extra="forbid") on EVERY request model, so
    unknown fields are rejected rather than silently ignored
  - Money = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
  - Qty   = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]
    (gt=0 is the schema-level closure of P0-3)
  - list length bounds on every collection field
  - a custom JSON encoder emitting Decimal as a STRING, never a float, so
    the client never sees 249.00000000000003

TASK 2 — Blueprints under src/vglpos/api/v1/
  auth.py, sales.py, products.py, customers.py, reports.py, shifts.py,
  sync.py, settings.py. Implement the endpoint map in
  VGL_POS_Architecture_Review.md §6.2.

TASK 3 — Cross-cutting middleware
  - Idempotency: an @idempotent decorator keyed on the Idempotency-Key
    header, storing (key, request_hash, response) in Redis for 24h. A replay
    with the same key and same body returns the stored response; the same
    key with a DIFFERENT body returns 409. Required on all POST/PUT/PATCH.
  - RFC 7807 error responses for every failure, carrying request_id.
  - Cursor pagination helper (keyset, not offset).
  - Tiered rate limits, Redis-backed: login 5/15min per username AND per IP,
    checkout 120/min per terminal, reports 20/min per user, exports 5/hour.
  - An ETag/If-None-Match path on the product catalogue endpoint.

TASK 4 — POST /api/v1/sales/quote
  A dry-run pricing endpoint returning the full computed tax breakup WITHOUT
  persisting. The front-end calls this to display totals so that the number
  on screen is always the number the server will charge. The client must
  never compute a total itself.

TASK 5 — OpenAPI 3.1
  Generated from the Pydantic models, not hand-written. Served at
  /api/v1/openapi.json with Swagger UI at /api/v1/docs (auth-gated in prod).
  A contract test asserts every registered route appears in the spec.

TASK 6 — Tests
  tests/api/ with at least one success and one failure case per endpoint:
    - 401 without a token, 403 with the wrong permission
    - 422 with a malformed body, 422 with an unknown extra field
    - idempotent replay returns the identical response body
    - Decimal fields serialise as strings
    - cursor pagination returns stable results across insertions

CONSTRAINTS
- No route function longer than 25 lines.
- No route imports a model directly; it goes through a service.
- Every route decorated with @require_permission.

GATE
  pytest tests/api -v
  curl -s localhost:8000/api/v1/openapi.json | python -m json.tool > /dev/null
  pytest -k "test_openapi_covers_every_route" -v
  # Manual: POST the same sale twice with one Idempotency-Key -> one sale row
  psql -c "SELECT COUNT(*) FROM sales WHERE offline_uuid = '<uuid>'"   # 1
```

---

## PHASE 4 — Performance

```
ROLE: Senior performance engineer, PostgreSQL + SQLAlchemy.

CONTEXT
The prototype's measured query counts on a tiny seeded dataset:
  GET /api/sales?per_page=20            55 queries  (N+1 via to_dict)
  GET /api/customers                     7 queries  (per-customer aggregation)
  GET /api/reports/revenue?period=365   732 queries (Python day-loop)
There were zero indexes in the entire schema.

TASK 1 — Instrument first
  Add a pytest fixture `assert_max_queries(n)` that counts SQL statements via
  a SQLAlchemy before_cursor_execute event and fails the test if exceeded.
  Then write a test per endpoint asserting its query budget. These tests are
  the regression guard — they must fail the build if anyone reintroduces N+1.

TASK 2 — Eliminate N+1
  - selectinload / joinedload on every collection endpoint. Choose
    selectinload for one-to-many (avoids the cartesian product).
  - customers.total_spent and total_orders are denormalised counters updated
    in checkout_service. Add a reconciliation CLI command that recomputes and
    reports drift, run nightly by Celery beat.
  - Never serialise a lazy relationship in a response DTO. Add a test that
    fails if any DTO construction triggers a lazy load (use SQLAlchemy's
    raiseload('*') in the test fixture).

TASK 3 — Replace loop-aggregation with SQL
  report_service.revenue_series must be ONE query:
    SELECT date_trunc('day', business_date) AS d, SUM(net_amount),
           COUNT(*) FROM sales WHERE ... GROUP BY d ORDER BY d
  Gap-fill missing days in Python. Same for the dashboard's 7-day series.

TASK 4 — Indexes
  Add every index from the architecture review §5.2 as a migration, using
  CREATE INDEX CONCURRENTLY. Then produce docs/query_plans.md containing
  EXPLAIN (ANALYZE, BUFFERS) output BEFORE and AFTER for the ten hottest
  queries, against a seeded dataset of 100k sales / 5k products / 2k
  customers. Every plan must show an index scan, not a sequential scan.

TASK 5 — Caching
  - Redis for flask-caching and flask-limiter (the prototype used per-process
    memory, so limits multiplied by worker count).
  - Cache the product catalogue and the dashboard summary, invalidated by
    domain EVENTS (SaleCompleted, ProductUpdated), not by a timeout. Cache
    keys must include company_id and branch_id.
  - mv_daily_sales_summary refreshed CONCURRENTLY every 5 minutes by Celery
    beat; reports read the view.

TASK 6 — Barcode fast path
  GET /api/v1/products/lookup?barcode= must be a single indexed row fetch
  with no joins and no serialisation of relationships. Target p99 < 10ms
  measured at 100k products. Add a benchmark test.

TASK 7 — Load testing
  tests/load/locustfile.py simulating 50 concurrent cashiers, each: search,
  scan 5 barcodes, quote, checkout, every 6 seconds. Assert p99 checkout
  < 500ms and error rate 0. Wire into CI as a nightly job.

DELIVERABLES
  docs/query_plans.md, docs/performance_baseline.md with before/after numbers
  in a table, and the query-budget tests.

GATE
  pytest tests/performance -v
  # Query budgets that MUST hold:
  #   GET /api/v1/sales?limit=20        <= 4 queries
  #   GET /api/v1/customers?limit=50    <= 2 queries
  #   GET /api/v1/reports/revenue?days=365  <= 2 queries
  #   GET /api/v1/products/lookup?barcode=X == 1 query
  locust -f tests/load/locustfile.py --headless -u 50 -r 5 -t 5m \
    --host http://localhost:8000
  psql -c "SELECT schemaname,relname,seq_scan,idx_scan FROM pg_stat_user_tables
           ORDER BY seq_scan DESC LIMIT 10"   # no hot table dominated by seq_scan
```

---

## PHASE 5 — Front-end rebuild

**This is the phase your cashiers will actually feel.** It is also where the "lighter, faster, more user-friendly" brief is delivered.

```
ROLE: Senior front-end engineer with retail POS domain experience.

CONTEXT
The prototype's front-end problems, measured:
  - Chart.js (~200KB) loads render-blocking in <head> on EVERY page,
    including the POS terminal which has no chart
  - Bootstrap CDN (~230KB) + 42KB unminified custom CSS
  - Google Fonts: Inter at 6 weights + Noto Sans Tamil at 4 = ~10 files
  - ~2,800 lines of INLINE JavaScript across 9 templates, forcing
    'unsafe-inline' in the CSP and preventing any caching
  - addToCart() calls window.prompt() for quantity on EVERY item — a cashier
    billing 20 items dismisses 20 native OS dialogs
  - the cart total is parsed back out of the DOM with .replace(',','') which
    replaces only the FIRST comma, so "₹1,00,000.00" parses as 100.00
  - no barcode scanner handling at all
  - cart state is a volatile JS array — a refresh loses the bill

TASK 1 — Asset diet. Targets, which I will measure:
    CSS on the POS page          < 40 KB
    JS on the POS page           < 45 KB
    Fonts                        < 90 KB total
    First Contentful Paint (3G)  < 1.5 s
    Lighthouse Performance       > 90
  Do it by:
    a) Removing Chart.js from base.html; load it ONLY in the scripts block of
       dashboard and reports. (This one change removes ~200KB from the
       billing screen.)
    b) defer on every remaining script.
    c) Dropping Bootstrap entirely. The existing style.css already defines
       the design tokens; build the ~15 components actually used
       (button, card, modal, toast, table, input, badge, spinner, tabs) on
       those tokens. Ship one minified stylesheet.
    d) Self-hosting fonts: Inter 400/600 and Noto Sans Tamil 400/600 only,
       subset to Latin + Tamil ranges, woff2, font-display: swap, preload
       the two used above the fold.
    e) Extracting ALL inline JS into ES modules under static/src/js/,
       content-hashed at build time, and REMOVING 'unsafe-inline' from the
       CSP script-src. Add a test that fails if any template contains an
       inline <script> with executable content or an on* attribute.
  Use esbuild or vite. Output to static/dist/ with a manifest the Jinja
  templates read for hashed filenames.

TASK 2 — Rebuild the POS screen around speed
  a) REMOVE window.prompt() entirely. Clicking or scanning a product adds
     quantity 1 IMMEDIATELY with a brief highlight animation. Quantity is
     edited on the cart line (the +/-/number controls already exist).
     For products flagged is_weighed, an inline numeric pad slides in.
  b) BARCODE SCANNER as a first-class input:
     - a global keydown listener that detects a scanner by its signature:
       >= 4 characters arriving with inter-key gaps < 30ms, terminated by
       Enter, no modifier keys
     - it works regardless of which element has focus
     - on Enter: call /api/v1/products/lookup?barcode=, add qty 1
     - the SAME barcode within 2 seconds increments the existing line rather
       than adding a duplicate
     - unknown barcode: a non-blocking toast offering "Add new product?" with
       the barcode prefilled
     - distinct audio feedback for hit and miss (cashiers work by ear)
  c) FULL KEYBOARD MAP, displayed on screen and in a F1 overlay:
     F1 help · F2 pay · F3 search · F4 hold bill · F5 recall bill ·
     F6 customer · F7 discount · F8 quantity · F9 reprint last ·
     F10 shift close · Esc clear/close · +/- adjust focused line
     Every one must work without touching the mouse.
  d) PAYMENT PAD: large tap targets for ₹100/₹200/₹500/₹2000 and "exact
     amount"; change due rendered very large (cashiers read it across the
     counter); split tender UI allowing up to 5 payment rows.
  e) TOTALS COME FROM THE SERVER. Call POST /api/v1/sales/quote (debounced
     150ms) after every cart mutation and display its response. The client
     NEVER computes a total. This structurally eliminates the class of bug
     in P3-1 and guarantees the screen matches the invoice.
  f) CART PERSISTENCE: mirror cart state to IndexedDB on every mutation;
     restore on load. A refresh or a crash must not lose the bill.

TASK 3 — UX gaps to close
  - Skeleton loaders, not spinners, on grid and table load
  - Optimistic add-to-cart (render before the server responds, reconcile after)
  - Replace every window.confirm() with a styled modal naming the item and
    the value at risk
  - Replace destructive confirmations with a 5-second undo toast where the
    action is reversible
  - Empty states with a call to action ("No products yet — import a CSV")
  - Error states that say what to do, not just what failed
  - aria-live="polite" on the toast container; focus trap in modals with
    focus returned to the trigger on close
  - Minimum 44x44px touch targets (the current qty-btn is ~28px)
  - prefers-reduced-motion respected
  - WCAG 2.2 AA contrast verified in BOTH themes — provide the audit table

TASK 4 — Real i18n
  Replace the "render both languages, toggle with a CSS class" approach
  (which doubles DOM size) and the hardcoded JS dictionary of Tamil category
  names. Build: JSON message catalogues per locale, a t(key, params) helper,
  name_en/name_ta columns read from the API, Intl.NumberFormat('en-IN') and
  Intl.DateTimeFormat('ta-IN') for numbers and dates. Adding a third locale
  must require zero template edits.

TASK 5 — Thermal receipt
  A dedicated print stylesheet for 58mm and 80mm rolls, selectable in
  settings: monospace, correct character width, no colour, no background,
  QR block reserved for the future IRN. Plus an A5 tax-invoice layout for
  B2B. Test both by actually printing to PDF at the target width.

CONSTRAINTS
- No SPA framework. Server-rendered Jinja + ES modules + Alpine.js (~15KB)
  for reactivity only.
- No new runtime dependency over 20KB without justifying it to me first.
- Every interactive element reachable and operable by keyboard.

GATE
  npm run build
  # Measured on the /pos route:
  #   total transferred bytes < 200 KB
  #   Lighthouse Performance > 90, Accessibility > 95
  grep -rn "<script>" src/vglpos/web/templates | grep -v "src=" # must be empty
  grep -rn "unsafe-inline" src/vglpos    # must be empty
  grep -rn "prompt(" static/src          # must be empty
  npx playwright test tests/e2e/billing.spec.ts
  # Manual with a real USB scanner: scan 20 items in under 30 seconds,
  # mouse untouched, then pay by split tender and print.
```

---

## PHASE 6 — Offline PWA

```
ROLE: Senior engineer, offline-first web applications.

CONTEXT
An Indian retail counter loses connectivity regularly. Billing must not stop.
Competing products treat offline billing as table stakes. Design decision
already made: WRITE-AHEAD ONLY, not bidirectional sync. The counter creates
sales offline; master data is read-only offline. This avoids conflict
resolution entirely while covering the real failure mode.

TASK 1 — Service worker (static/src/sw.js), Workbox or hand-rolled
  - Cache-first with versioned precache for the app shell (HTML, CSS, JS,
    fonts, icons)
  - Network-first with a cache fallback for GET data endpoints
  - Never cache POST responses
  - A skipWaiting/clientsClaim update flow with a visible "New version —
    reload" prompt; never auto-reload mid-bill

TASK 2 — IndexedDB (idb wrapper), stores:
  products   full catalogue, delta-synced via
             GET /api/v1/products/catalog?since=<iso timestamp>
             (a full 5k-SKU download on every open is what makes competitors'
             PWAs feel slow — implement the delta properly)
  customers  frequently used subset
  cart       current bill, written on every mutation
  outbox     pending sales, each with a client-generated UUID
  meta       last sync timestamps, catalogue version

TASK 3 — Offline checkout
  - The bill is computed LOCALLY using a JavaScript port of the tax engine.
    CRITICAL: this port must be verified against the Python engine. Generate
    a shared fixture file of 200 scenarios; a CI job runs both engines over
    it and fails on any divergence to the paisa. Do not hand-maintain two
    implementations without this gate.
  - Provisional invoice number: '<terminal>-OFF-<seq>'. The receipt prints
    with a clear "provisional" marker. The server assigns the real series
    number on sync and the reprint shows it.
  - Stock is decremented optimistically in the local cache with a clear
    "unverified" indicator on low-stock items.

TASK 4 — Outbox drain
  - Background Sync API where available; a polling fallback (every 30s while
    online) where not.
  - POST /api/v1/sync/batch takes an array of operations, each idempotent on
    its UUID, and returns per-operation results.
  - Partial failure handling: successes are removed from the outbox, failures
    are retried with exponential backoff, and permanent failures (e.g. stock
    genuinely unavailable) are surfaced to the user in a review queue that
    they must resolve. NEVER silently drop a bill.
  - Cap the outbox at 500 entries; beyond that, block new offline bills and
    alert loudly. A terminal offline for three days is a business problem,
    not a sync problem.

TASK 5 — UI
  - Persistent, unmissable status: "Online" / "Offline — 3 bills queued" /
    "Syncing 3 of 7"
  - A queue review screen listing pending and failed bills
  - Warn before closing a shift with a non-empty outbox

TASK 6 — Tests
  - Playwright with network offline: complete a bill, go online, assert one
    sale row appears with the correct totals
  - Submit the same offline UUID twice: assert exactly one sale row
  - Cross-engine parity test (Python vs JS) over the 200-scenario fixture
  - Outbox cap enforcement
  - Catalogue delta sync returns only changed rows

CONSTRAINTS
- Never lose a bill. Every failure path ends in either a synced sale or a
  visible item in the review queue.
- The offline tax engine must be a build artefact generated from, or
  verified against, the Python source — never a divergent hand-written copy.

GATE
  npx playwright test tests/e2e/offline.spec.ts
  pytest tests/integration/test_sync.py -v
  npm run test:tax-parity        # 200 scenarios, zero divergence
  # Manual: pull the network cable, bill 5 customers, reconnect,
  # verify 5 sales with correct sequential invoice numbers.
```

---

## PHASE 7 — Retail operations

```
ROLE: Senior engineer with retail POS domain experience.

CONTEXT
The core billing loop works. Now add the operational features a real shop
needs daily, which the prototype lacked entirely.

TASK 1 — Shift and cash drawer management
  - open_shift(terminal, cashier, opening_float, denomination_counts)
    One OPEN shift per terminal, enforced by a partial unique index.
  - Cash movements during the shift: PAY_IN, PAY_OUT, DROP, FLOAT_ADD,
    each with a mandatory reason and an audit row.
  - close_shift with a BLIND count: the cashier enters counted denominations
    WITHOUT seeing the expected figure first. The variance is revealed after
    submission. This is the standard anti-shrinkage control; do not show the
    expected total on the counting screen.
  - Variance over a configurable threshold requires a manager PIN and a
    written explanation.
  - Z-report: sales by payment method, voids, returns, discounts given,
    no-sale drawer opens, expected vs counted, variance, tax summary.
    Printable on the thermal roll.
  - A sale cannot be created without an open shift on that terminal.

TASK 2 — Hold and recall bills
  - Park a bill with an optional label (customer name, "blue shirt guy").
  - A recall screen showing parked bills with age, item count, value.
  - Parked bills do NOT reserve stock, and this must be shown to the user.
  - Auto-expire parked bills at shift close with a prompt to resolve them.

TASK 3 — Split tender
  Multiple sale_payments rows per sale, up to 5. Validation: the sum must
  cover the payable; change may only be given against the CASH portion. A
  UPI/card row requires a reference. Partial credit (khata) requires the
  customer to have a credit limit and updates customers.outstanding.

TASK 4 — Loyalty redemption
  Points as a tender type. Configurable earn rate (default 1 point per ₹10)
  and redemption rate (default 1 point = ₹0.25). Redemption capped at a
  configurable percentage of the bill. Points are reversed proportionally on
  a return. Every points movement gets a ledger row — never mutate the
  balance without one.

TASK 5 — Quick keys and favourites
  A configurable grid of the top-selling and pinned products per terminal,
  bindable to number keys. For a tea shop this is the entire interface.

TASK 6 — Receipt delivery
  - Thermal print (58/80mm)
  - WhatsApp (already prototyped — move it to a Celery task with retry, and
    remove the hardcoded BASE_URL)
  - SMS via a pluggable provider interface
  - Email for B2B invoices with the A5 PDF attached
  - A "reprint last bill" action bound to F9, permission-gated and audited
    (reprint is a known fraud vector)

TASK 7 — Product management improvements
  - CSV/Excel import with a dry-run preview, per-row validation, and a
    downloadable error report. This is how a shop onboards 3,000 SKUs.
  - Bulk price update by category or percentage, with an approval step and
    full price history.
  - Barcode label printing (Code128 / EAN13) with configurable label sizes.
  - Product image upload with server-side resize.

TASK 8 — Tests
  Shift lifecycle including the variance path; sale rejected with no open
  shift; split tender arithmetic including the change-from-cash-only rule;
  points earn/redeem/reverse; parked bill lifecycle; CSV import happy path
  and every validation failure.

GATE
  pytest tests/integration/test_shifts.py tests/integration/test_payments.py -v
  npx playwright test tests/e2e/shift-lifecycle.spec.ts
  # Manual: open a shift with ₹2000 float, bill 10 customers across cash,
  # UPI, split and points, do a return, close with a deliberate ₹50 shortage,
  # confirm the Z-report shows exactly ₹50 variance and demands an explanation.
```

---

## PHASE 8 — Business depth

```
ROLE: Senior ERP engineer, Indian retail and GST domain.

CONTEXT
Billing is solid. Now build the modules that make this a business system
rather than a till: purchasing, real inventory, and statutory reporting.

TASK 1 — Purchase and supplier management
  - Supplier master with GSTIN, state code, payment terms, outstanding.
  - Purchase order -> Goods Receipt Note -> supplier invoice matching, with
    tolerance settings for quantity and price variance.
  - Purchase entry updates stock via stock_ledger and recalculates the
    weighted average cost. Show the cost change before committing.
  - Purchase returns (debit notes) with their own number series and tax.
  - Supplier ledger and ageing report.
  - Landed cost allocation (freight, loading) apportioned across lines by
    value or weight.

TASK 2 — Inventory depth
  - Batch and expiry tracking with FEFO allocation at sale time. A near-expiry
    dashboard and a configurable block-or-warn policy on expired stock.
    (Required for pharmacy, dairy, packaged food.)
  - Product variants: a parent product with size/colour/style children
    sharing HSN and tax but with distinct SKUs, barcodes and stock.
    (Required for textiles.)
  - Physical stock audit: generate a count sheet, enter counts, review the
    variance, post adjustments with reasons — all through stock_ledger.
  - Multi-branch stock transfer with in-transit status.
  - Reorder suggestions from sales velocity, lead time and safety stock.
  - Stock valuation report at cost and at retail.

TASK 3 — GST statutory reporting
  - GSTR-1: B2B (invoice-wise), B2CL, B2CS (rate-wise summary), CDNR
    (credit/debit notes), HSN summary with UQC, and Documents Issued
    (the number ranges used, issued, cancelled). Export in the government's
    JSON schema AND as an offline-utility-compatible Excel.
  - GSTR-3B summary figures.
  - A reconciliation report: books vs GSTR-1, flagging any invoice whose
    components do not sum to its total (this must always be empty, and is
    the standing regression guard for the P0-4 class of bug).
  - HSN-wise tax summary and a rate-wise sales register.
  - Tally XML export (Sales/Purchase/Journal vouchers) — the single most
    requested integration, because the shop's CA uses Tally.

TASK 4 — Financial reporting
  - Gross margin by product, category, brand and supplier, using
    sale_items.cost_at_sale (the cost snapshot taken at sale time, not
    today's cost).
  - Day book, cash book, customer and supplier outstanding ageing.
  - Sales comparison across periods, and by hour of day for staffing.

TASK 5 — Tests
  Every report gets a fixture dataset with HAND-CALCULATED expected output.
  Specifically for GSTR-1: build a 30-invoice fixture covering B2B, B2C,
  interstate, credit notes and nil-rated, and assert the generated JSON
  matches a hand-verified expected file exactly.

CONSTRAINTS
- Every report is generated from the same service layer as the UI, so the
  numbers on screen and in the export can never diverge.
- Long reports run as Celery jobs with a download link, not a blocking HTTP
  request.

GATE
  pytest tests/integration/test_gstr1.py -v
  pytest tests/integration/test_purchases.py tests/integration/test_batches.py -v
  # Manual: generate GSTR-1 for a month and validate the JSON in the
  # government's offline utility. It must load with zero errors.
  # Manual: import the Tally XML into a Tally trial company.
```

---

## PHASE 9 — E-invoicing and compliance

```
ROLE: Senior integration engineer, Indian GST e-invoicing.

CONTEXT
E-invoicing is mandatory for businesses with aggregate annual turnover above
₹5 crore (PAN-level, if crossed in ANY financial year since 2017-18 — a
business that crosses once never drops back out). The threshold has moved
downward repeatedly since 2020 and is widely expected to fall further, so
build the adapter before it is needed.

TASK 1 — IRP integration
  - A provider-agnostic interface (IRPClient) with concrete adapters, since
    businesses connect via different GSPs. Start with the NIC sandbox.
  - Auth token management with caching and refresh.
  - Map a Sale to the e-invoice JSON schema (currently 1.1): seller, buyer,
    item list with HSN and UQC, value details, tax breakup. Validate against
    the schema locally BEFORE sending — the IRP's error messages are terse.
  - Handle IRN generation, cancellation (within 24 hours), and the
    duplicate-IRN response (which means it already succeeded — treat it as
    success, not failure).
  - Store IRN, AckNo, AckDate and the signed QR payload; render the QR on
    the receipt and the A5 invoice.

TASK 2 — Resilience. This is the part that matters.
  - E-invoice generation is a Celery task. A sale is NEVER blocked on IRP
    availability — the customer walks out with a bill regardless.
  - Retry with exponential backoff and jitter; a dead-letter queue after N
    attempts; an admin screen listing failures with the IRP's error text and
    a retry button.
  - An alert if the pending queue exceeds 50 or the oldest pending exceeds
    the reporting window (currently 30 days for qualifying taxpayers, and
    proposals to shorten it have been discussed — make the window
    configurable).
  - A reconciliation job comparing sales against IRNs and reporting gaps.

TASK 3 — E-way bill
  Generation for applicable consignments, with distance and transporter
  details, sharing the same resilience pattern.

TASK 4 — Compliance controls
  - Invoice cancellation window enforcement (same day, pre-filing).
  - "Documents issued" tracking for GSTR-1: numbers allocated, used,
    cancelled, per series.
  - Composition dealer mode: no tax on the invoice plus the mandatory
    declaration text.
  - Configurable invoice templates meeting Rule 46 field requirements, with
    a validation check that every mandatory field is populated before a bill
    can be issued.

TASK 5 — Tests
  - Full sandbox integration test against the NIC test environment.
  - Mocked failure modes: timeout, 5xx, invalid schema, duplicate IRN,
    expired token — each must leave the sale intact and the task retryable.
  - A test asserting a sale completes successfully with the IRP entirely
    unreachable.

GATE
  pytest tests/integration/test_einvoice.py -v
  # Manual: generate an IRN against the NIC sandbox and verify the QR with
  # the government's verification app.
  # Manual: block outbound network to the IRP, complete 10 sales, confirm all
  # 10 bill normally and all 10 appear in the pending queue, then restore the
  # network and confirm all 10 obtain IRNs.
```

---

## PHASE 10 — Hardening and operations

```
ROLE: Senior DevOps / SRE engineer.

CONTEXT
Feature-complete. Now make it operable by someone who did not write it, and
survivable when things go wrong.

TASK 1 — Observability
  - structlog JSON to stdout, every line carrying request_id, user_id,
    company_id, branch_id.
  - Sentry for exceptions, with PII scrubbing (no GSTIN, phone, or customer
    name in event payloads).
  - Prometheus metrics: http_request_duration_seconds (histogram, by route),
    checkout_total, checkout_failures_total (by reason), offline_queue_depth,
    einvoice_pending_total, shift_variance_rupees, db_pool_in_use.
  - Grafana dashboards: business (bills/hour, revenue, avg bill value) and
    technical (latency, errors, pool, queue depth). Provision as code.
  - Alerts with runbook links: p99 checkout > 1s for 5 min; error rate > 1%;
    offline queue > 100; e-invoice pending > 50; backup job failed; disk
    > 80%; replication lag > 30s.

TASK 2 — Backup and disaster recovery
  - Nightly pg_dump plus continuous WAL archiving to object storage,
    encrypted at rest with a key NOT stored alongside the backups.
  - 30-day retention, with monthly archives kept for 8 years (the GST record
    retention requirement).
  - A restore_drill.sh that provisions a scratch database, restores the
    latest backup, runs an integrity suite (row counts, SUM checks, the
    reconciliation query), reports RTO, and tears down. Run it MONTHLY in CI
    and fail loudly if it fails. An untested backup is not a backup.
  - Document RPO (15 min) and RTO (1 hour) and prove both in the drill.

TASK 3 — Deployment
  - Blue/green or rolling deploy with a health-gated cutover.
  - Migrations run as a SEPARATE release step, never at application boot.
  - A documented, tested rollback: previous image + alembic downgrade -1.
  - Feature flags for anything risky, so a bad feature can be turned off
    without a deploy.
  - A pre-deploy checklist and a post-deploy smoke suite.

TASK 4 — Security hardening
  - pip-audit and npm audit in CI, failing on high severity.
  - A dependency update policy and Dependabot.
  - Secrets from a managed store, with a documented rotation procedure.
  - The app's DB role has INSERT-only on audit_log — verify with a test that
    attempts an UPDATE and expects a permission error.
  - Rate limits verified under load.
  - A penetration test checklist covering the OWASP Top 10, with the
    POS-specific threats from the architecture review §9.2 added.

TASK 5 — Documentation
  - docs/runbook.md: how to restart, roll back, restore, clear a stuck
    queue, handle a failed migration, respond to each alert.
  - docs/architecture.md with C4 diagrams.
  - docs/api.md generated from OpenAPI.
  - docs/onboarding.md: a new engineer productive in one day.
  - docs/user-guide-ta.md and -en.md: cashier and owner guides, with
    screenshots, in both languages.
  - docs/gst-compliance.md: which rule each feature satisfies, for the CA.

TASK 6 — Final verification
  - A full load test at 3x expected peak.
  - A chaos exercise: kill the database mid-checkout, kill Redis, kill a
    worker, fill the disk. Document the observed behaviour and fix anything
    that loses data.
  - A complete audit-trail walkthrough: pick a random sale and demonstrate
    who created it, from which terminal, in which shift, what it contained,
    what tax applied, whether it was returned, and what the stock impact was.

GATE
  ./scripts/restore_drill.sh              # passes, RTO reported
  locust --headless -u 150 -r 10 -t 15m   # p99 within budget, 0 errors
  pytest tests/security -v
  pip-audit --strict && npm audit --audit-level=high
  # Manual: perform a full rollback on staging and confirm the system
  # returns to the previous version with data intact.
```

---

## Appendix A — Verification prompt (run at every phase boundary)

Paste this in a FRESH session, so the agent that wrote the code is not the
agent that reviews it:

```
ROLE: Independent senior code reviewer. You did not write this code. Your job
is to find what is wrong with it, not to praise it.

CONTEXT
Review the changes on branch phase-N-<name> against the standing engineering
rules in CLAUDE.md and the phase gate criteria in
VGL_POS_Rebuild_Prompt_Pack.md.

CHECK, and report findings with file:line references:
1. Any `float` used for money, anywhere, including intermediate values.
2. Any business logic in a route handler.
3. Any database query not scoped by company_id.
4. Any API route without a permission decorator.
5. Any schema change without a working Alembic downgrade.
6. Any bare except, any `except Exception: pass`, any swallowed error.
7. Any TODO, FIXME, placeholder, stub, or `...` function body.
8. Any hardcoded secret, hostname, GSTIN, phone number or store name.
9. Any test that asserts nothing meaningful, or that would still pass if the
   implementation were deleted.
10. Any N+1 query pattern.
11. Any place where a client-supplied value is trusted for pricing, tax,
    stock or identity.
12. Any coverage threshold that was lowered rather than met.

Then, independently:
- Run the phase gate commands and report actual output, not expected output.
- Pick the three most complex functions added and explain what each does and
  what happens on its failure paths. If you cannot explain one clearly, say
  so — that is a finding.
- List anything the phase prompt asked for that is missing or only partially
  implemented.

Output a table: SEVERITY | FILE:LINE | FINDING | SUGGESTED FIX.
Do not fix anything. Report only.
```

---

## Appendix B — What to do when the agent goes wrong

| Symptom | Cause | Response |
|---|---|---|
| Invents a business rule | Ambiguous prompt | Add the rule to CLAUDE.md and restart the phase |
| Writes tests that pass trivially | Wrote code and tests together | Use the Appendix A reviewer in a separate session; write the golden-file expectations yourself |
| Drifts into refactoring adjacent code | Scope not fenced | Interrupt immediately. Add "do not modify files outside X" to the prompt |
| Lowers a coverage threshold | Taking the easy path | Revert. This is a standing rule violation |
| Claims a gate passes without running it | Assumed rather than verified | Always run gates yourself. Never accept a reported result |
| Produces a 2000-line file | No structural constraint | Add explicit file/function size limits to the prompt |
| Hallucinates a library API | Unfamiliar or new library | Ask it to read the installed package source before using it |

## Appendix C — Sequencing rules

1. **Phase 0 ships today.** Everything else can wait; those holes cannot.
2. **Never skip 1C.** Every rupee the system will ever handle passes through
   that code. Hand-verify the golden files yourself.
3. **Phase 5 before Phase 7.** A fast, pleasant billing screen with fewer
   features beats a feature-rich slow one. Cashiers vote with their hands.
4. **Phase 6 before any multi-store rollout.** Offline is not optional in
   Indian retail.
5. **Do not start Phase 8 until a real shop has run on Phases 0–7 for two
   weeks.** Real usage will change your Phase 8 priorities more than any
   plan will.
6. **Re-run every prior phase's gate before merging a new phase.** The gates
   are your regression suite; they only work if they all keep passing.

