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

