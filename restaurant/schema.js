export const VERSION = 3;
export const TABLES = {
  settings: ["id", "value"],
  products: [
    "id",
    "name",
    "portion",
    "category",
    "price_paise",
    "image",
    "active",
  ],
  customers: ["id", "name", "phone", "city"],
  sequences: ["fy", "last_number"],
  sales: [
    "id",
    "operation_id",
    "request",
    "bill_number",
    "fy",
    "sequence_number",
    "created_at",
    "customer",
    "identity",
    "mode",
    "tax_bps",
    "tax_inclusive",
    "round_rupee",
    "gross_paise",
    "discount_paise",
    "tax_paise",
    "round_paise",
    "total_paise",
  ],
  sale_lines: [
    "sale_id",
    "position",
    "product_id",
    "name",
    "portion",
    "quantity",
    "unit_paise",
    "gross_paise",
    "discount_paise",
    "net_paise",
    "tax_inclusive",
    "tax_paise",
    "taxable_paise",
    "cgst_paise",
    "sgst_paise",
  ],
  payments: [
    "sale_id",
    "position",
    "method",
    "amount_paise",
    "tendered_paise",
    "change_paise",
  ],
  adjustments: [
    "id",
    "operation_id",
    "sale_id",
    "kind",
    "amount_paise",
    "reason",
    "created_at",
  ],
  adjustment_payments: ["adjustment_id", "method", "amount_paise"],
  print_attempts: ["id", "sale_id", "created_at", "state", "detail"],
  drafts: ["id", "value"],
};

// Independent restaurant schema: no tenant, inventory, purchase, or remote queue entities.
export const SCHEMA = `
CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS settings(id TEXT PRIMARY KEY CHECK(id='store'), value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY, name TEXT NOT NULL, portion TEXT NOT NULL, category TEXT NOT NULL, price_paise INTEGER NOT NULL CHECK(price_paise>0 AND typeof(price_paise)='integer'), image TEXT, active INTEGER NOT NULL CHECK(active IN(0,1)));
CREATE TABLE IF NOT EXISTS customers(id TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT NOT NULL, city TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sequences(fy TEXT PRIMARY KEY, last_number INTEGER NOT NULL CHECK(last_number>0));
CREATE TABLE IF NOT EXISTS sales(id TEXT PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE, request TEXT NOT NULL, bill_number TEXT NOT NULL UNIQUE, fy TEXT NOT NULL, sequence_number INTEGER NOT NULL CHECK(sequence_number>0), created_at TEXT NOT NULL, customer TEXT NOT NULL, identity TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN('training','bill_of_supply','tax_invoice')), tax_bps INTEGER NOT NULL, tax_inclusive INTEGER NOT NULL DEFAULT 1 CHECK(tax_inclusive IN(0,1)), round_rupee INTEGER NOT NULL CHECK(round_rupee IN(0,1)), gross_paise INTEGER NOT NULL CHECK(gross_paise>=0), discount_paise INTEGER NOT NULL CHECK(discount_paise>=0 AND discount_paise<=gross_paise), tax_paise INTEGER NOT NULL CHECK(tax_paise>=0), round_paise INTEGER NOT NULL, total_paise INTEGER NOT NULL CHECK(total_paise>=0 AND total_paise=gross_paise-discount_paise+(1-tax_inclusive)*tax_paise+round_paise), UNIQUE(fy,sequence_number));
CREATE TABLE IF NOT EXISTS sale_lines(sale_id TEXT NOT NULL REFERENCES sales(id), position INTEGER NOT NULL, product_id TEXT NOT NULL, name TEXT NOT NULL, portion TEXT NOT NULL, quantity INTEGER NOT NULL CHECK(quantity>0), unit_paise INTEGER NOT NULL CHECK(unit_paise>0), gross_paise INTEGER NOT NULL CHECK(gross_paise=quantity*unit_paise), discount_paise INTEGER NOT NULL CHECK(discount_paise>=0 AND discount_paise<=gross_paise), net_paise INTEGER NOT NULL CHECK(net_paise=gross_paise-discount_paise+(1-tax_inclusive)*tax_paise), tax_inclusive INTEGER NOT NULL DEFAULT 1 CHECK(tax_inclusive IN(0,1)), tax_paise INTEGER NOT NULL CHECK(tax_paise>=0), taxable_paise INTEGER NOT NULL CHECK(taxable_paise+tax_paise=net_paise), cgst_paise INTEGER NOT NULL, sgst_paise INTEGER NOT NULL CHECK(cgst_paise+sgst_paise=tax_paise), PRIMARY KEY(sale_id,position));
CREATE TABLE IF NOT EXISTS payments(sale_id TEXT NOT NULL REFERENCES sales(id), position INTEGER NOT NULL CHECK(position>=0 AND position<2), method TEXT NOT NULL CHECK(method IN('cash','upi')), amount_paise INTEGER NOT NULL CHECK(amount_paise>=0 AND typeof(amount_paise)='integer'), tendered_paise INTEGER NOT NULL, change_paise INTEGER NOT NULL CHECK(change_paise=tendered_paise-amount_paise AND change_paise>=0), PRIMARY KEY(sale_id,position), UNIQUE(sale_id,method));
CREATE TABLE IF NOT EXISTS adjustments(id TEXT PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE, sale_id TEXT NOT NULL REFERENCES sales(id), kind TEXT NOT NULL CHECK(kind IN('void','refund')), amount_paise INTEGER NOT NULL CHECK(amount_paise>=0), reason TEXT NOT NULL CHECK(length(trim(reason))>0), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS adjustment_payments(adjustment_id TEXT NOT NULL REFERENCES adjustments(id), method TEXT NOT NULL CHECK(method IN('cash','upi')), amount_paise INTEGER NOT NULL CHECK(amount_paise>=0 AND typeof(amount_paise)='integer'), PRIMARY KEY(adjustment_id,method));
CREATE TABLE IF NOT EXISTS print_attempts(id TEXT PRIMARY KEY, sale_id TEXT NOT NULL REFERENCES sales(id), created_at TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN('requested','submitted','cancelled','failed')), detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sales_created_at ON sales(created_at);
CREATE INDEX IF NOT EXISTS adjustments_sale_id ON adjustments(sale_id);
CREATE INDEX IF NOT EXISTS adjustments_created_at ON adjustments(created_at);
`;

// Exact historical column contracts are used before converting old backups.
export const V2_TABLES = Object.fromEntries(Object.entries(TABLES).map(([name, columns]) =>
  [name, columns.filter(column => column !== "tax_inclusive")],
));
export const LEGACY_TABLES = Object.fromEntries(
  Object.entries(V2_TABLES)
    .filter(([name]) => name !== "adjustment_payments")
    .map(([name, columns]) => [
      name,
      name === "payments" ? columns.filter((c) => c !== "position") : columns,
    ]),
);
export const PAYMENT_SCHEMA =
  "CREATE TABLE IF NOT EXISTS payments(sale_id TEXT NOT NULL REFERENCES sales(id), position INTEGER NOT NULL CHECK(position>=0 AND position<2), method TEXT NOT NULL CHECK(method IN('cash','upi')), amount_paise INTEGER NOT NULL CHECK(amount_paise>=0 AND typeof(amount_paise)='integer'), tendered_paise INTEGER NOT NULL, change_paise INTEGER NOT NULL CHECK(change_paise=tendered_paise-amount_paise AND change_paise>=0), PRIMARY KEY(sale_id,position), UNIQUE(sale_id,method));";

/** Rebuild constrained financial tables atomically with foreign keys kept enabled. */
export async function migrateGstPricing(db) {
  const names = ["sales", "sale_lines", "payments", "adjustments", "adjustment_payments", "print_attempts"];
  const pattern = new RegExp("\\b(" + names.join("|") + ")\\b", "g");
  for (const name of names) {
    const create = SCHEMA.match(new RegExp("CREATE TABLE IF NOT EXISTS " + name + "\\([^;]+;"))[0];
    await db.exec(create.replace(pattern, match => match + "_gst_v3"));
    const columns = TABLES[name];
    await db.exec(`INSERT INTO ${name}_gst_v3(${columns.join(",")}) SELECT ${columns.map(column => column === "tax_inclusive" ? "1" : column).join(",")} FROM ${name};`);
  }
  for (const name of [...names].reverse()) await db.exec(`DROP TABLE ${name};`);
  for (const name of names) await db.exec(`ALTER TABLE ${name}_gst_v3 RENAME TO ${name};`);
  await db.exec(SCHEMA);
  if ((await db.query("PRAGMA foreign_key_check")).length)
    throw new Error("GST migration references are invalid");
}
