# VGL POS Phase 1B entity relationship diagram

This diagram reflects the complete model registry. Audit actor relationships
(`created_by`, `updated_by`, `deleted_by` → `users.id`) are omitted from the
diagram to keep the business relationships readable.

```mermaid
erDiagram
    companies ||--o{ branches : owns
    companies ||--o{ terminals : owns
    branches ||--o{ terminals : contains

    companies ||--o{ users : employs
    companies ||--o{ roles : defines
    companies ||--o{ role_permissions : scopes
    companies ||--o{ user_roles : scopes
    roles ||--o{ role_permissions : grants
    permissions ||--o{ role_permissions : included_in
    users ||--o{ user_roles : receives
    roles ||--o{ user_roles : assigned_as
    branches o|--o{ user_roles : limits

    companies ||--o{ tax_rates : configures
    tax_rates o|--o{ hsn_codes : default_for
    companies ||--o{ categories : organises
    categories o|--o{ categories : parent_of
    companies ||--o{ products : sells
    categories o|--o{ products : classifies
    hsn_codes o|--o{ products : codes
    tax_rates ||--o{ products : taxes
    companies ||--o{ product_barcodes : scopes
    products ||--o{ product_barcodes : identifies
    companies ||--o{ product_price_history : scopes
    products ||--o{ product_price_history : repriced
    users ||--o{ product_price_history : changed_by

    companies ||--o{ customers : serves
    companies ||--o{ suppliers : buys_from

    companies ||--o{ document_series : numbers
    branches ||--o{ document_series : numbers
    companies ||--o{ sales : records
    branches ||--o{ sales : records
    terminals ||--o{ sales : bills
    customers o|--o{ sales : purchases
    users ||--o{ sales : cashier
    shifts o|--o{ sales : contains
    companies ||--o{ sale_items : scopes
    sales ||--|{ sale_items : contains
    products ||--o{ sale_items : sold_as
    companies ||--o{ sale_payments : scopes
    sales ||--|{ sale_payments : tendered_by
    companies ||--o{ credit_notes : records
    branches ||--o{ credit_notes : issues
    sales ||--o{ credit_notes : reversed_by
    companies ||--o{ credit_note_items : scopes
    credit_notes ||--|{ credit_note_items : contains
    sale_items ||--o{ credit_note_items : reverses

    companies ||--o{ stock_batches : owns
    branches ||--o{ stock_batches : stores
    products ||--o{ stock_batches : batched_as
    companies ||--o{ stock_ledger : owns
    branches ||--o{ stock_ledger : records
    products ||--o{ stock_ledger : moves
    stock_batches o|--o{ stock_ledger : tracks
    companies ||--o{ purchases : owns
    branches ||--o{ purchases : receives
    suppliers ||--o{ purchases : supplies
    companies ||--o{ purchase_items : scopes
    purchases ||--|{ purchase_items : contains
    products ||--o{ purchase_items : purchased_as

    companies ||--o{ shifts : owns
    branches ||--o{ shifts : operates
    terminals ||--o{ shifts : opens
    users ||--o{ shifts : cashier
    companies ||--o{ cash_movements : scopes
    shifts ||--o{ cash_movements : records
    companies ||--o{ audit_log : owns
```
