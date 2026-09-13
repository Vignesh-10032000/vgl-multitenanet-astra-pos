# VGL POS — Architecture Review & Target DDL Specification

**Document Reference:** `VGL_POS_Architecture_Review.md`  
**System:** Vignesh Growth Lab Point of Sale (VGL POS) Rebuild  
**Architecture Author:** Claude (Fable / Sonnet Architecture Session)  
**Companion Documents:**
- `VGL_POS_Rebuild_Prompt_Pack.md` (Phased Rebuild Blueprint)
- `CLAUDE.md` (Standing Engineering Rules)
- `HOTFIX_NOTES.md` (Phase 0 Emergency Security Hotfixes)

---

## 1. Executive Summary & Audit Findings

The VGL POS prototype (`POS-project-main`) demonstrated strong product-market fit for Indian retail workflows but contained critical architectural, security, and financial integrity liabilities identified during the comprehensive audit:

1. **Financial Integrity**: Floating-point money columns (`Float`) causing rounding discrepancies; pre-discount tax apportionment violating Indian GST reconciliation (`taxable + cgst + sgst != net_amount`).
2. **Tenancy & Isolation**: Monolithic single-tenant schema lacking company/branch isolation; vulnerable to cross-tenant data leakage.
3. **Security Posture**: Unauthenticated administrative endpoints (`POST /api/demo/reset`), unbounded checkout input (negative quantities, unbounded discounts), stored XSS in UI rendering, and permissive CORS.
4. **Performance & Scalability**: Synchronous blocking request handling, N+1 ORM queries, lack of database indexing on high-frequency ledger and sales lookups, and per-process memory rate-limiting.

This document defines the **Target Architecture**, the **Complete §5.2 Target DDL & Indexing Strategy**, the **§6.2 API Endpoint Contracts**, and the **§9.2 POS-Specific Threat Model**.

---

## 2. Standing Engineering Rules & Invariants

All models, migrations, and application code must adhere to the four non-negotiable rules:

| Rule | Requirement | Machine Verification |
|---|---|---|
| **Zero Float Rule** | All currency must use `decimal.Decimal` and PostgreSQL `NUMERIC(14,2)`. Quantities must use `NUMERIC(12,3)`. Python `float` and SQLAlchemy `Float` are strictly prohibited. | Introspection test scanning `metadata.tables` fails build on any `Float` column. |
| **Strict Tenancy** | Every table (except pure global lookups) must include a non-nullable `company_id BIGINT` foreign key. `company_id` is never accepted from client HTTP bodies/query strings; it must be derived from verified JWT claims. | URL-map and query-inspection tests verify tenancy scoping. |
| **Strict Schema Governance** | All database mutations must occur via versioned Alembic migrations. Every migration must provide an idempotent, working `downgrade()` script. `db.create_all()` is forbidden. | Migration rollback CI test (`alembic upgrade head -> downgrade base -> upgrade head`). |
| **Largest-Remainder GST Apportionment** | Line discounts and taxes must be apportioned using the largest-remainder method so that line items sum exactly to header values with zero paisa error. | Golden-file test suite with 20 real-world edge-case receipts. |

---

## 5. Target Data Architecture & DDL

### §5.1 Schema Design Principles
1. **Surrogate Primary Keys**: Every table uses `BIGINT GENERATED ALWAYS AS IDENTITY` (mapped to `BigInteger` in SQLAlchemy).
2. **Audit Mixin**: Every table carries:
   - `created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL`
   - `created_by BIGINT REFERENCES users(id) ON DELETE RESTRICT`
   - `updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL`
   - `updated_by BIGINT REFERENCES users(id) ON DELETE RESTRICT`
   - `deleted_at TIMESTAMP WITH TIME ZONE NULL` (Soft delete)
   - `deleted_by BIGINT REFERENCES users(id) ON DELETE RESTRICT`
   - `row_version INTEGER DEFAULT 1 NOT NULL` (Optimistic concurrency control)
3. **Soft Delete Partial Indexes**: Unique constraints must use partial unique indexes filtering `WHERE deleted_at IS NULL` to allow re-use of unique codes/SKUs after deletion.
4. **Explicit Foreign Key Policies**: Default is `ON DELETE RESTRICT`. `ON DELETE CASCADE` is permitted only for dependent child items of an aggregate root (e.g. `sale_items`, `credit_note_items`, `role_permissions`).

---

### §5.2 Target DDL & Indexing Specification

The database is built across 7 sequential migration blocks:

```
001_core_tenancy   --> companies, branches, terminals
002_identity       --> users, roles, permissions, role_permissions, user_roles
003_tax_catalogue  --> tax_rates, hsn_codes, categories, products, product_barcodes, product_price_history
004_parties        --> customers, suppliers
005_documents      --> document_series, sales, sale_items, sale_payments, credit_notes, credit_note_items
006_inventory      --> stock_ledger, stock_batches, purchases, purchase_items
007_shifts_audit   --> shifts, cash_movements, audit_log (partitioned), mv_daily_sales_summary
```

---

#### Migration 001: Core Tenancy (`001_core_tenancy`)

```sql
-- 1. COMPANIES (Top-level tenant)
CREATE TABLE companies (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    legal_name VARCHAR(255) NOT NULL,
    gstin VARCHAR(15) NULL,
    pan VARCHAR(10) NULL,
    cin VARCHAR(21) NULL,
    state_code VARCHAR(2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'INR' NOT NULL,
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255) NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    postal_code VARCHAR(10) NOT NULL,
    contact_email VARCHAR(255) NOT NULL,
    contact_phone VARCHAR(20) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_companies_gstin ON companies (gstin) WHERE deleted_at IS NULL AND gstin IS NOT NULL;
CREATE INDEX idx_companies_active ON companies (is_active) WHERE deleted_at IS NULL;

-- 2. BRANCHES
CREATE TABLE branches (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    gstin VARCHAR(15) NULL,
    state_code VARCHAR(2) NOT NULL,
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255) NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100) NOT NULL,
    postal_code VARCHAR(10) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    is_head_office BOOLEAN DEFAULT FALSE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_branches_company_code ON branches (company_id, code) WHERE deleted_at IS NULL;
CREATE INDEX idx_branches_company_id ON branches (company_id);

-- 3. TERMINALS (Registers)
CREATE TABLE terminals (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    code VARCHAR(50) NOT NULL,
    name VARCHAR(255) NOT NULL,
    terminal_type VARCHAR(50) DEFAULT 'COUNTER' NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    last_seen_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_terminals_branch_code ON terminals (branch_id, code) WHERE deleted_at IS NULL;
CREATE INDEX idx_terminals_branch_id ON terminals (branch_id);
CREATE INDEX idx_terminals_company_id ON terminals (company_id);
```

---

#### Migration 002: Identity & RBAC (`002_identity`)

```sql
-- 4. USERS
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    phone VARCHAR(20) NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    is_superuser BOOLEAN DEFAULT FALSE NOT NULL,
    failed_login_attempts INTEGER DEFAULT 0 NOT NULL,
    locked_until TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_users_company_username ON users (company_id, username) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX uq_users_company_email ON users (company_id, email) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_company_id ON users (company_id);

-- 5. ROLES
CREATE TABLE roles (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    description TEXT NULL,
    is_system BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_roles_company_name ON roles (company_id, name) WHERE deleted_at IS NULL;

-- 6. PERMISSIONS
CREATE TABLE permissions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL
);

-- 7. ROLE_PERMISSIONS (Mapping)
CREATE TABLE role_permissions (
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    permission_id BIGINT NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
    PRIMARY KEY (role_id, permission_id)
);

-- 8. USER_ROLES (Mapping)
CREATE TABLE user_roles (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role_id BIGINT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    branch_id BIGINT NULL REFERENCES branches(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);
```

---

#### Migration 003: Tax Catalogue (`003_tax_catalogue`)

```sql
-- 9. TAX_RATES
CREATE TABLE tax_rates (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    rate NUMERIC(5,2) NOT NULL,
    cgst_rate NUMERIC(5,2) NOT NULL,
    sgst_rate NUMERIC(5,2) NOT NULL,
    igst_rate NUMERIC(5,2) NOT NULL,
    cess_rate NUMERIC(5,2) DEFAULT 0.00 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL,
    CONSTRAINT ck_tax_rates_components CHECK (cgst_rate + sgst_rate = rate OR igst_rate = rate)
);

CREATE UNIQUE INDEX uq_tax_rates_company_name ON tax_rates (company_id, name) WHERE deleted_at IS NULL;

-- 10. HSN_CODES
CREATE TABLE hsn_codes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code VARCHAR(10) NOT NULL UNIQUE,
    description VARCHAR(255) NOT NULL,
    default_tax_rate_id BIGINT NULL REFERENCES tax_rates(id) ON DELETE RESTRICT
);

-- 11. CATEGORIES
CREATE TABLE categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) NOT NULL,
    parent_id BIGINT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    icon VARCHAR(50) NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_categories_company_code ON categories (company_id, code) WHERE deleted_at IS NULL;

-- 12. PRODUCTS
CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    category_id BIGINT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    hsn_id BIGINT NULL REFERENCES hsn_codes(id) ON DELETE RESTRICT,
    tax_rate_id BIGINT NOT NULL REFERENCES tax_rates(id) ON DELETE RESTRICT,
    barcode VARCHAR(64) NULL,
    uom VARCHAR(20) DEFAULT 'UNIT' NOT NULL,
    cost_price NUMERIC(14,2) NOT NULL,
    selling_price NUMERIC(14,2) NOT NULL,
    mrp NUMERIC(14,2) NOT NULL,
    is_tax_inclusive BOOLEAN DEFAULT FALSE NOT NULL,
    is_inventory_tracked BOOLEAN DEFAULT TRUE NOT NULL,
    low_stock_threshold NUMERIC(12,3) DEFAULT 5.000 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL,
    CONSTRAINT ck_products_prices CHECK (cost_price >= 0 AND selling_price >= 0 AND mrp >= selling_price)
);

CREATE UNIQUE INDEX uq_products_company_sku ON products (company_id, sku) WHERE deleted_at IS NULL;
CREATE INDEX idx_products_company_category ON products (company_id, category_id);
CREATE INDEX idx_products_barcode ON products (company_id, barcode) WHERE barcode IS NOT NULL;

-- 13. PRODUCT_BARCODES
CREATE TABLE product_barcodes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    barcode VARCHAR(64) NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE NOT NULL
);

CREATE UNIQUE INDEX uq_product_barcodes_code ON product_barcodes (barcode);
CREATE INDEX idx_product_barcodes_product ON product_barcodes (product_id);

-- 14. PRODUCT_PRICE_HISTORY
CREATE TABLE product_price_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    old_selling_price NUMERIC(14,2) NOT NULL,
    new_selling_price NUMERIC(14,2) NOT NULL,
    old_mrp NUMERIC(14,2) NOT NULL,
    new_mrp NUMERIC(14,2) NOT NULL,
    effective_from TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    changed_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT
);
```

---

#### Migration 004: Parties (`004_parties`)

```sql
-- 15. CUSTOMERS
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    phone VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NULL,
    gstin VARCHAR(15) NULL,
    state_code VARCHAR(2) DEFAULT '33' NOT NULL,
    loyalty_points NUMERIC(12,3) DEFAULT 0.000 NOT NULL,
    credit_limit NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    outstanding_balance NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    address TEXT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_customers_company_phone ON customers (company_id, phone) WHERE deleted_at IS NULL;
CREATE INDEX idx_customers_company_name ON customers (company_id, name);

-- 16. SUPPLIERS
CREATE TABLE suppliers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    name VARCHAR(255) NOT NULL,
    code VARCHAR(50) NOT NULL,
    contact_person VARCHAR(255) NULL,
    phone VARCHAR(20) NOT NULL,
    email VARCHAR(255) NULL,
    gstin VARCHAR(15) NULL,
    pan VARCHAR(10) NULL,
    state_code VARCHAR(2) NOT NULL,
    address TEXT NULL,
    payment_terms_days INTEGER DEFAULT 30 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_suppliers_company_code ON suppliers (company_id, code) WHERE deleted_at IS NULL;
```

---

#### Migration 005: Documents & Billing (`005_documents`)

```sql
-- 17. DOCUMENT_SERIES
CREATE TABLE document_series (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    doc_type VARCHAR(50) NOT NULL,
    prefix VARCHAR(20) NOT NULL,
    current_number BIGINT DEFAULT 0 NOT NULL,
    financial_year VARCHAR(10) NOT NULL,
    suffix VARCHAR(20) NULL,
    CONSTRAINT uq_series_branch_type_fy UNIQUE (branch_id, doc_type, financial_year)
);

-- 18. SALES (Invoice Aggregate Root)
CREATE TABLE sales (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    terminal_id BIGINT NOT NULL REFERENCES terminals(id) ON DELETE RESTRICT,
    customer_id BIGINT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    cashier_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    shift_id BIGINT NULL,
    invoice_number VARCHAR(64) NOT NULL,
    business_date DATE NOT NULL,
    sale_status VARCHAR(50) DEFAULT 'COMPLETED' NOT NULL,
    supply_type VARCHAR(20) DEFAULT 'INTRASTATE' NOT NULL,
    gross_amount NUMERIC(14,2) NOT NULL,
    discount_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    taxable_amount NUMERIC(14,2) NOT NULL,
    cgst_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    sgst_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    igst_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    cess_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    round_off NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    net_amount NUMERIC(14,2) NOT NULL,
    amount_paid NUMERIC(14,2) NOT NULL,
    balance_due NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    cancelled_at TIMESTAMPTZ NULL,
    cancellation_reason TEXT NULL,
    notes TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL,
    CONSTRAINT ck_sales_reconcile CHECK (
        taxable_amount + cgst_amount + sgst_amount + igst_amount + cess_amount + round_off = net_amount
    ),
    CONSTRAINT ck_sales_tax_mode CHECK (
        (cgst_amount > 0 AND sgst_amount > 0 AND igst_amount = 0) OR
        (cgst_amount = 0 AND sgst_amount = 0 AND igst_amount >= 0) OR
        (cgst_amount = 0 AND sgst_amount = 0 AND igst_amount = 0)
    )
);

CREATE UNIQUE INDEX uq_sales_company_invoice ON sales (company_id, invoice_number);
CREATE INDEX idx_sales_branch_business_date ON sales (branch_id, business_date);
CREATE INDEX idx_sales_customer ON sales (customer_id);

-- 19. SALE_ITEMS
CREATE TABLE sale_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_id BIGINT NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    line_number INTEGER NOT NULL,
    quantity NUMERIC(12,3) NOT NULL,
    unit_price NUMERIC(14,2) NOT NULL,
    gross_amount NUMERIC(14,2) NOT NULL,
    discount_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    taxable_amount NUMERIC(14,2) NOT NULL,
    tax_rate NUMERIC(5,2) NOT NULL,
    cgst_rate NUMERIC(5,2) DEFAULT 0.00 NOT NULL,
    sgst_rate NUMERIC(5,2) DEFAULT 0.00 NOT NULL,
    igst_rate NUMERIC(5,2) DEFAULT 0.00 NOT NULL,
    cess_rate NUMERIC(5,2) DEFAULT 0.00 NOT NULL,
    cgst_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    sgst_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    igst_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    cess_amount NUMERIC(14,2) DEFAULT 0.00 NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL,
    CONSTRAINT ck_sale_items_qty CHECK (quantity > 0)
);

CREATE INDEX idx_sale_items_sale_id ON sale_items (sale_id);
CREATE INDEX idx_sale_items_product_id ON sale_items (product_id);

-- 20. SALE_PAYMENTS (Tender splitting)
CREATE TABLE sale_payments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_id BIGINT NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    payment_method VARCHAR(50) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    reference_number VARCHAR(100) NULL,
    processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- 21. CREDIT_NOTES (Sales returns)
CREATE TABLE credit_notes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    original_sale_id BIGINT NOT NULL REFERENCES sales(id) ON DELETE RESTRICT,
    credit_note_number VARCHAR(64) NOT NULL,
    reason VARCHAR(50) NOT NULL,
    net_amount NUMERIC(14,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_credit_notes_number ON credit_notes (company_id, credit_note_number);

-- 22. CREDIT_NOTE_ITEMS
CREATE TABLE credit_note_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    credit_note_id BIGINT NOT NULL REFERENCES credit_notes(id) ON DELETE CASCADE,
    original_sale_item_id BIGINT NOT NULL REFERENCES sale_items(id) ON DELETE RESTRICT,
    quantity NUMERIC(12,3) NOT NULL,
    amount NUMERIC(14,2) NOT NULL
);
```

---

#### Migration 006: Inventory & Stock (`006_inventory`)

```sql
-- 23. STOCK_BATCHES
CREATE TABLE stock_batches (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    batch_number VARCHAR(100) NOT NULL,
    mfg_date DATE NULL,
    expiry_date DATE NULL,
    cost_price NUMERIC(14,2) NOT NULL,
    selling_price NUMERIC(14,2) NOT NULL,
    quantity_received NUMERIC(12,3) NOT NULL,
    quantity_available NUMERIC(12,3) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE UNIQUE INDEX uq_batches_product_number ON stock_batches (branch_id, product_id, batch_number) WHERE deleted_at IS NULL;
CREATE INDEX idx_batches_expiry ON stock_batches (branch_id, expiry_date);

-- 24. STOCK_LEDGER (Double-entry movement history)
CREATE TABLE stock_ledger (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    batch_id BIGINT NULL REFERENCES stock_batches(id) ON DELETE RESTRICT,
    txn_type VARCHAR(50) NOT NULL,
    reference_id VARCHAR(100) NOT NULL,
    reference_type VARCHAR(50) NOT NULL,
    quantity NUMERIC(12,3) NOT NULL,
    balance_after NUMERIC(12,3) NOT NULL,
    unit_cost NUMERIC(14,2) NOT NULL,
    notes TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL
);

CREATE INDEX idx_stock_ledger_product_lookup ON stock_ledger (branch_id, product_id, created_at DESC);
CREATE INDEX idx_stock_ledger_reference ON stock_ledger (reference_type, reference_id);

-- 25. PURCHASES
CREATE TABLE purchases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    supplier_id BIGINT NOT NULL REFERENCES suppliers(id) ON DELETE RESTRICT,
    invoice_number VARCHAR(100) NOT NULL,
    invoice_date DATE NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

-- 26. PURCHASE_ITEMS
CREATE TABLE purchase_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    purchase_id BIGINT NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
    batch_number VARCHAR(100) NULL,
    quantity NUMERIC(12,3) NOT NULL,
    unit_cost NUMERIC(14,2) NOT NULL,
    tax_rate NUMERIC(5,2) NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL
);
```

---

#### Migration 007: Shifts, Cash & Audit Log (`007_shifts_audit`)

```sql
-- 27. SHIFTS (Cash drawer control)
CREATE TABLE shifts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    branch_id BIGINT NOT NULL REFERENCES branches(id) ON DELETE RESTRICT,
    terminal_id BIGINT NOT NULL REFERENCES terminals(id) ON DELETE RESTRICT,
    cashier_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    opened_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    closed_at TIMESTAMPTZ NULL,
    opening_cash NUMERIC(14,2) NOT NULL,
    closing_cash_expected NUMERIC(14,2) NULL,
    closing_cash_counted NUMERIC(14,2) NULL,
    cash_difference NUMERIC(14,2) NULL,
    status VARCHAR(20) DEFAULT 'OPEN' NOT NULL,
    notes TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NULL,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_by BIGINT NULL,
    deleted_at TIMESTAMPTZ NULL,
    deleted_by BIGINT NULL,
    row_version INTEGER DEFAULT 1 NOT NULL
);

CREATE INDEX idx_shifts_open ON shifts (terminal_id) WHERE status = 'OPEN';

-- 28. CASH_MOVEMENTS (Float / Drop / Payout)
CREATE TABLE cash_movements (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    shift_id BIGINT NOT NULL REFERENCES shifts(id) ON DELETE CASCADE,
    movement_type VARCHAR(20) NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT
);

-- 29. AUDIT_LOG (Immutable, Range Partitioned by Year/Month)
CREATE TABLE audit_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    company_id BIGINT NOT NULL,
    user_id BIGINT NULL,
    action VARCHAR(50) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(100) NOT NULL,
    old_values JSONB NULL,
    new_values JSONB NULL,
    ip_address VARCHAR(45) NULL,
    user_agent TEXT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Partition examples:
CREATE TABLE audit_log_y2026m07 PARTITION OF audit_log
    FOR VALUES FROM ('2026-07-01 00:00:00+00') TO ('2026-08-01 00:00:00+00');
CREATE TABLE audit_log_y2026m08 PARTITION OF audit_log
    FOR VALUES FROM ('2026-08-01 00:00:00+00') TO ('2026-09-01 00:00:00+00');
CREATE TABLE audit_log_y2026m09 PARTITION OF audit_log
    FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00');

-- 30. MATERIALIZED VIEW: DAILY SALES SUMMARY
CREATE MATERIALIZED VIEW mv_daily_sales_summary AS
SELECT 
    company_id,
    branch_id,
    business_date,
    COUNT(id) AS total_bills,
    SUM(gross_amount) AS total_gross,
    SUM(discount_amount) AS total_discount,
    SUM(taxable_amount) AS total_taxable,
    SUM(cgst_amount) AS total_cgst,
    SUM(sgst_amount) AS total_sgst,
    SUM(igst_amount) AS total_igst,
    SUM(round_off) AS total_round_off,
    SUM(net_amount) AS total_net
FROM sales
WHERE sale_status = 'COMPLETED' AND deleted_at IS NULL
GROUP BY company_id, branch_id, business_date;

CREATE UNIQUE INDEX uq_mv_daily_sales ON mv_daily_sales_summary (branch_id, business_date);
```

---

## 6. API Architecture & Endpoint Contracts (§6.2)

### §6.1 Cross-Cutting Middleware Standards
1. **Idempotency**: All `POST`, `PUT`, `PATCH` endpoints enforce an `@idempotent` decorator. Clients provide an `Idempotency-Key: <UUIDv4>` header. Redis stores `(key, sha256(request_body), response)` with a 24-hour TTL. Duplicate requests with matching payloads return the cached response; differing payloads return `HTTP 409 Conflict`.
2. **Standardized Error Format (RFC 7807)**: Every failure returns `application/problem+json` carrying a unique `request_id`.
3. **Cursor Keyset Pagination**: High-cardinality endpoints (sales, products, ledger) strictly prohibit `OFFSET/LIMIT`. Keyset pagination operates on `(created_at, id)`.
4. **Redis Tiered Rate Limits**:
   - Authentication: 5 attempts per 15 min per username & IP.
   - Cashier Checkout: 120 requests/min per terminal.
   - Analytical Reports: 20 requests/min per user.
   - Bulk Data Exports: 5 requests/hour per user.

### §6.2 Complete Route Blueprint Map

| Blueprint | Route / Method | Description | RBAC Permission |
|---|---|---|---|
| **`auth.py`** | `POST /api/v1/auth/login` | Authenticates username & password (Argon2id), issues JWT access/refresh tokens. | Public |
| | `POST /api/v1/auth/refresh` | Rotates JWT refresh token and issues new access token. | Public |
| | `POST /api/v1/auth/logout` | Revokes active JWT tokens in Redis blocklist. | Authenticated |
| | `GET /api/v1/auth/me` | Returns current user profile, company, branch, and role permissions. | Authenticated |
| **`sales.py`** | `POST /api/v1/sales/checkout` | Validates cart, verifies stock, executes Largest-Remainder GST math, writes double-entry stock ledger, and generates fiscal invoice. | `sales:checkout` |
| | `GET /api/v1/sales` | Keyset cursor-paginated list of sales with date, cashier, and status filters. | `sales:read` |
| | `GET /api/v1/sales/<id>` | Full invoice details including lines, tax apportionment, and payments. | `sales:read` |
| | `POST /api/v1/sales/<id>/cancel` | Soft-cancels sale, restores stock ledger, records cancellation audit. | `sales:cancel` |
| | `POST /api/v1/sales/<id>/receipt/whatsapp` | Enqueues Celery task to dispatch WhatsApp PDF receipt link. | `sales:receipt` |
| **`products.py`**| `GET /api/v1/products` | Fast cached catalog listing with full-text search and barcode resolution. | `catalog:read` |
| | `POST /api/v1/products` | Creates new product with SKU, HSN, tax rate, and pricing tiers. | `catalog:write` |
| | `PUT /api/v1/products/<id>` | Updates product details and emits price history audit log on change. | `catalog:write` |
| | `DELETE /api/v1/products/<id>`| Soft-deletes product (retaining ledger references). | `catalog:delete` |
| **`customers.py`**| `GET /api/v1/customers` | Searches customers by phone or name. | `customers:read` |
| | `POST /api/v1/customers` | Creates new customer record with optional GSTIN for B2B. | `customers:write` |
| | `GET /api/v1/customers/<id>` | Customer details, balance, and past purchase history. | `customers:read` |
| **`shifts.py`** | `POST /api/v1/shifts/open` | Starts register shift with opening cash float. | `shifts:operate` |
| | `POST /api/v1/shifts/cash-movement` | Records cash-in, cash-out, pay-in, pay-out. | `shifts:operate` |
| | `POST /api/v1/shifts/close` | Closes shift with blind cash count reconciliation. | `shifts:close` |
| **`reports.py`** | `GET /api/v1/reports/daily-summary` | Queries `mv_daily_sales_summary` for fast end-of-day reconciliation. | `reports:view` |
| | `GET /api/v1/reports/gstr1` | Generates GSTR-1 B2B (Table 4A), B2C Large (5A), and B2C Small (7) JSON. | `reports:export` |
| | `GET /api/v1/reports/inventory-valuation` | FIFO / Weighted Average stock valuation report. | `reports:view` |
| **`sync.py`** | `POST /api/v1/sync/offline-push` | Receives and atomically commits offline sales batches queued during network drops. | `sync:push` |

---

## 9. Security & Threat Model Specification (§9.2)

Retail POS systems in Indian counter environments are subject to high-risk insider threats, network tampering, and financial fraud. The following threat matrix outlines mandatory defensive controls:

| Threat Vector | Attack Scenario | Defensive Countermeasure |
|---|---|---|
| **T-1: Unauthenticated Database Reset** | Attacker or rogue cashier calls test reset endpoints (`/api/demo/reset`) to wipe evidence of skimming. | All test/demo routes exist solely under `APP_ENV=demo` and require constant-time `X-Demo-Token` HMAC validation. Fail-closed architecture returns 404 for unmounted routes. |
| **T-2: Negative Quantity / Price Tampering** | Client manipulates checkout payload with negative quantity (`{"qty": -5}`) or price below cost to generate refunds or reduce bill amount. | Server-side DTO validation rejecting non-positive quantities (`ck_sale_items_qty`), database CHECK constraints, and pricing looked up exclusively from the DB catalog (client prices are ignored). |
| **T-3: Cross-Tenant Data Leakage** | Tenant A passes `company_id=2` in query string to read another store's sales or inventory. | Strict tenancy enforcement: `company_id` is extracted exclusively from cryptographic JWT claims and injected into SQL query boundaries. |
| **T-4: Offline Batch Tampering & Replay** | Cashier tampers with client-side IndexedDB queue while offline to alter timestamps, discounts, or cash totals before sync. | Every offline transaction carries an HMAC signature generated with terminal hardware keys. The server recalculates taxes and verifies invoice reconciliation before committing. |
| **T-5: Cash Drawer Skimming (Blind Count Bypass)** | Cashier sees expected drawer cash and steals difference before counting. | Shift closing UI requires **blind cash counting** — expected totals are hidden until the cashier enters the physical denomination counts and confirms. |
| **T-6: Stock Manipulation without Trace** | Employee alters product inventory counts to cover stolen goods. | Direct column stock updates (`UPDATE products SET stock = ...`) are banned. Stock mutations must flow through the append-only `stock_ledger` table with mandatory transaction references. |
| **T-7: Stored XSS in Receipts & Display** | Malicious product name (e.g. `<script>steal()</script>`) injected to steal tokens when viewed by store manager. | Strict HTML entity escaping (`escapeHtml()`) across all client DOM updates; Content Security Policy (CSP) blocking inline script execution; Jinja server auto-escaping on receipts. |

---

## 10. Verification Gates & Compliance

- **Alembic Verification**: Every migration must be tested with `alembic upgrade head` followed by `alembic downgrade base` and re-upgrade.
- **MyPy Strict Typing**: 100% type-annotated domain models and repositories with zero type errors under `--strict`.
- **Zero Float Compliance**: Automated test scanning SQLAlchemy metadata guaranteeing zero `Float` columns across the entire database catalog.
