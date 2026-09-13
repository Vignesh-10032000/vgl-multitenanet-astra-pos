BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001

INSERT INTO alembic_version (version_num) VALUES ('0001') RETURNING alembic_version.version_num;

-- Running upgrade 0001 -> 0002

CREATE TABLE companies (
    id SERIAL NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    gstin VARCHAR(15), 
    address_line1 VARCHAR(255), 
    address_line2 VARCHAR(255), 
    city VARCHAR(100), 
    state VARCHAR(100), 
    state_code VARCHAR(2), 
    postal_code VARCHAR(20), 
    contact_name VARCHAR(100), 
    contact_phone VARCHAR(20), 
    contact_email VARCHAR(255), 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_companies PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_companies_gstin ON companies (gstin);

UPDATE alembic_version SET version_num='0002' WHERE alembic_version.version_num = '0001';

-- Running upgrade 0002 -> 0003

CREATE TABLE branches (
    id SERIAL NOT NULL, 
    company_id INTEGER NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    code VARCHAR(50), 
    address_line1 VARCHAR(255), 
    address_line2 VARCHAR(255), 
    city VARCHAR(100), 
    state VARCHAR(100), 
    state_code VARCHAR(2), 
    postal_code VARCHAR(20), 
    gstin VARCHAR(15), 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_branches PRIMARY KEY (id), 
    CONSTRAINT fk_branches_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT
);

CREATE INDEX ix_branches_company_id ON branches (company_id);

CREATE INDEX ix_branches_gstin ON branches (gstin);

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

-- Running upgrade 0003 -> 0004

CREATE TABLE registers (
    id SERIAL NOT NULL, 
    company_id INTEGER NOT NULL, 
    branch_id INTEGER NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    code VARCHAR(50) NOT NULL, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_registers PRIMARY KEY (id), 
    CONSTRAINT fk_registers_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_registers_branch_id_branches FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE RESTRICT
);

CREATE INDEX ix_registers_company_id ON registers (company_id);

CREATE INDEX ix_registers_branch_id ON registers (branch_id);

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

-- Running upgrade 0004 -> 0005

CREATE TABLE product_catalog (
    id SERIAL NOT NULL, 
    company_id INTEGER NOT NULL, 
    name VARCHAR(255) NOT NULL, 
    sku VARCHAR(100), 
    barcode VARCHAR(100), 
    category VARCHAR(100), 
    unit_of_measure VARCHAR(20) DEFAULT 'PCS' NOT NULL, 
    base_price NUMERIC(12, 2) NOT NULL, 
    mrp NUMERIC(12, 2) NOT NULL, 
    cost_price NUMERIC(12, 2), 
    hsn_code VARCHAR(10), 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_product_catalog PRIMARY KEY (id), 
    CONSTRAINT fk_product_catalog_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT
);

CREATE INDEX ix_product_catalog_company_id ON product_catalog (company_id);

CREATE INDEX ix_product_catalog_name ON product_catalog (name);

CREATE INDEX ix_product_catalog_sku ON product_catalog (sku);

CREATE INDEX ix_product_catalog_barcode ON product_catalog (barcode);

CREATE INDEX ix_product_catalog_category ON product_catalog (category);

CREATE INDEX ix_product_catalog_hsn_code ON product_catalog (hsn_code);

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

-- Running upgrade 0005 -> 0006

CREATE TABLE tax_rates (
    id SERIAL NOT NULL, 
    company_id INTEGER NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    cgst_rate NUMERIC(5, 2) DEFAULT 0.00 NOT NULL, 
    sgst_rate NUMERIC(5, 2) DEFAULT 0.00 NOT NULL, 
    igst_rate NUMERIC(5, 2) DEFAULT 0.00 NOT NULL, 
    hsn_code_pattern VARCHAR(20), 
    category VARCHAR(100), 
    effective_from DATE NOT NULL, 
    effective_to DATE, 
    is_active BOOLEAN DEFAULT true NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_tax_rates PRIMARY KEY (id), 
    CONSTRAINT fk_tax_rates_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT
);

CREATE INDEX ix_tax_rates_company_id ON tax_rates (company_id);

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

-- Running upgrade 0006 -> 0007

CREATE TYPE stock_movement_type AS ENUM ('purchase', 'sale', 'adjustment', 'transfer');

CREATE TYPE stock_movement_type AS ENUM ('purchase', 'sale', 'adjustment', 'transfer');

CREATE TABLE stock_ledger (
    id SERIAL NOT NULL, 
    company_id INTEGER NOT NULL, 
    branch_id INTEGER NOT NULL, 
    product_id INTEGER NOT NULL, 
    movement_type stock_movement_type NOT NULL, 
    quantity NUMERIC(12, 3) NOT NULL, 
    reference_doc_id VARCHAR(100), 
    notes VARCHAR(255), 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    CONSTRAINT pk_stock_ledger PRIMARY KEY (id), 
    CONSTRAINT fk_stock_ledger_company_id_companies FOREIGN KEY(company_id) REFERENCES companies (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_stock_ledger_branch_id_branches FOREIGN KEY(branch_id) REFERENCES branches (id) ON DELETE RESTRICT, 
    CONSTRAINT fk_stock_ledger_product_id_product_catalog FOREIGN KEY(product_id) REFERENCES product_catalog (id) ON DELETE RESTRICT
);

CREATE INDEX ix_stock_ledger_company_id ON stock_ledger (company_id);

CREATE INDEX ix_stock_ledger_branch_id ON stock_ledger (branch_id);

CREATE INDEX ix_stock_ledger_product_id ON stock_ledger (product_id);

CREATE INDEX ix_stock_ledger_movement_type ON stock_ledger (movement_type);

CREATE INDEX ix_stock_ledger_reference_doc_id ON stock_ledger (reference_doc_id);

UPDATE alembic_version SET version_num='0007' WHERE alembic_version.version_num = '0006';

-- Running upgrade 0007 -> 0008

CREATE INDEX ix_stock_ledger_company_product_created ON stock_ledger (company_id, product_id, created_at);

CREATE INDEX ix_stock_ledger_company_branch_product ON stock_ledger (company_id, branch_id, product_id);

CREATE INDEX ix_product_catalog_company_active_name ON product_catalog (company_id, is_active, name);

CREATE INDEX ix_tax_rates_company_active_effective ON tax_rates (company_id, is_active, effective_from);

CREATE UNIQUE INDEX ix_registers_company_branch_code ON registers (company_id, branch_id, code);

UPDATE alembic_version SET version_num='0008' WHERE alembic_version.version_num = '0007';

COMMIT;

