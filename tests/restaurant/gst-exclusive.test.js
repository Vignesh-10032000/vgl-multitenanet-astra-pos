import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import fc from "fast-check";
import ExcelJS from "exceljs";
import { quote } from "../../restaurant/domain.js";
import { Ledger } from "../../restaurant/repository.js";
import { TABLES, V2_TABLES, LEGACY_TABLES, VERSION } from "../../restaurant/schema.js";
import { createBackup, inspectBackup, restoreBackup } from "../../restaurant/backup.js";
import { receiptHTML } from "../../restaurant/documents.js";
import { datasets, xlsx } from "../../restaurant/exports.js";
import { digest } from "../../restaurant/assets.js";
import { setup, order, currentDefaults, defaults, menu, database, MemoryImages } from "./helpers.js";

const now = () => "2026-11-02T05:00:00.000Z";
const period = { from: "2026-11-01", to: "2026-11-30" };
const v2Schema = readFileSync(new URL("./fixtures/schema-v2.sql", import.meta.url), "utf8");
const project = (tables, shape) => Object.fromEntries(Object.entries(shape).map(([name, columns]) =>
  [name, tables[name].map(row => Object.fromEntries(columns.map(column => [column, row[column]])))],
));

async function historical() {
  const { ledger, db } = await setup({ now });
  try {
    const sale = await ledger.checkout(order());
    await ledger.adjust({ sale_id: sale.id, operation_id: "legacy-return", kind: "refund", amount_paise: 1000, reason: "Historical correction" });
    await ledger.saveDraft({ items: [{ product_id: "menu-002", quantity: 2 }] });
    await ledger.saveLocalSetting("owner-test-marker", { preserved: true });
    const tables = project(await ledger.snapshot(), V2_TABLES);
    for (const row of tables.settings) {
      const settings = JSON.parse(row.value);
      delete settings.tax_inclusive;
      delete settings.gst_pricing_revision;
      row.value = JSON.stringify(settings);
    }
    for (const row of tables.sales) {
      const identity = JSON.parse(row.identity);
      delete identity.tax_inclusive;
      delete identity.gst_pricing_revision;
      row.identity = JSON.stringify(identity);
    }
    return { tables, sale };
  } finally { await db.close(); }
}

async function v2Database(tables) {
  const db = database();
  await db.exec("PRAGMA foreign_keys=ON;" + v2Schema);
  await db.run("INSERT INTO schema_versions VALUES(2)");
  for (const [name, columns] of Object.entries(V2_TABLES))
    for (const row of tables[name])
      await db.run(`INSERT INTO ${name}(${columns.join(",")}) VALUES(${columns.map(() => "?").join(",")})`, columns.map(column => row[column]));
  return db;
}

test("GST-EXCLUSIVE-01 current menu base 170 adds 4.25 CGST and 4.25 SGST without rounding", async () => {
  assert.equal(currentDefaults.tax_inclusive, false);
  const { ledger, db } = await setup({ now, settings: currentDefaults });
  try {
    for (const product of await ledger.products())
      assert.equal(product.price_paise, menu.items.find(item => item.reference_id === product.id).price_paise);
    const request = order();
    const sale = await ledger.checkout(request);
    assert.equal(sale.gross_paise, 17000);
    assert.equal(sale.lines[0].unit_paise, 17000);
    assert.equal(sale.lines[0].taxable_paise, 17000);
    assert.equal(sale.lines[0].cgst_paise, 425);
    assert.equal(sale.lines[0].sgst_paise, 425);
    assert.equal(sale.total_paise, 17850);
    assert.equal(sale.payment.change_paise, 2150);
    assert.deepEqual(await ledger.checkout(request), sale);
    const html = await receiptHTML(sale, new MemoryImages());
    assert.match(html, /GST added to menu prices/);
    assert.match(html.replace(/<[^>]*>/g, ""), /Taxable value: ₹170\.00/);
    assert.match(html.replace(/<[^>]*>/g, ""), /CGST 2\.5%: ₹4\.25/);
    assert.match(html.replace(/<[^>]*>/g, ""), /SGST 2\.5%: ₹4\.25/);
    assert.match(html, /₹178\.50/);
    await ledger.saveSettings({ ...await ledger.settings(), tax_inclusive: true });
    assert.deepEqual(await ledger.sale(sale.id), sale);
    assert.equal((await ledger.checkout(order())).total_paise, 17000);
  } finally { await db.close(); }
});

test("GST-EXCLUSIVE-02 independent integer oracle covers discounts, portions, odd paise and post-tax rounding", () => {
  fc.assert(fc.property(
    fc.array(fc.record({ unit_paise: fc.integer({ min: 1, max: 500000 }), quantity: fc.integer({ min: 1, max: 100 }) }), { minLength: 1, maxLength: 12 }),
    fc.nat(100000), fc.boolean(),
    (items, requestedDiscount, rounded) => {
      const gross = items.reduce((sum, line) => sum + line.unit_paise * line.quantity, 0);
      const discount = Math.min(gross, requestedDiscount);
      const result = quote(items, discount, { ...currentDefaults, round_rupee: rounded });
      let prior = 0n, accumulated = 0n, tax = 0n;
      for (const line of result.lines) {
        accumulated += BigInt(line.gross_paise);
        const allocation = BigInt(discount) * accumulated / BigInt(gross);
        const base = BigInt(line.gross_paise) - (allocation - prior);
        prior = allocation;
        const expectedTax = (base * 5n + 50n) / 100n;
        assert.equal(line.taxable_paise, Number(base));
        assert.equal(line.tax_paise, Number(expectedTax));
        assert.equal(line.net_paise, Number(base + expectedTax));
        assert.equal(line.cgst_paise + line.sgst_paise, Number(expectedTax));
        tax += expectedTax;
      }
      const due = BigInt(gross - discount) + tax;
      assert.equal(result.total_paise, Number(rounded ? (due + 50n) / 100n * 100n : due));
      assert.equal(result.taxable_paise + result.tax_paise + result.round_paise, result.total_paise);
    },
  ), { numRuns: 1500, seed: 20261102 });
  assert.equal(quote([{ quantity: 1, unit_paise: 17000 }], 1000, currentDefaults).total_paise, 16800);
  assert.throws(() => quote([{ quantity: 1, unit_paise: 100000000000 }], 0, currentDefaults));
  assert.throws(() => quote([{ quantity: 1, unit_paise: 17000 }], 0, { ...currentDefaults, tax_inclusive: "false" }));
});

test("GST-EXCLUSIVE-03 actual v2 database migration preserves every historical cell and changes only future price basis once", async () => {
  const { tables, sale } = await historical();
  const db = await v2Database(tables);
  const ledger = new Ledger(db, { now });
  try {
    await ledger.initialize(menu.items, currentDefaults);
    const migrated = await ledger.snapshot();
    for (const name of Object.keys(V2_TABLES).filter(name => name !== "settings"))
      assert.deepEqual(project(migrated, V2_TABLES)[name], tables[name], name);
    assert.equal((await ledger.sale(sale.id)).total_paise, 17000);
    assert.equal((await ledger.sale(sale.id)).tax_inclusive, 1);
    assert.equal((await ledger.settings()).tax_inclusive, false);
    assert.equal((await ledger.checkout(order())).total_paise, 17850);
    await ledger.saveSettings({ ...await ledger.settings(), tax_inclusive: true });
    await ledger.initialize(menu.items, currentDefaults);
    assert.equal((await ledger.settings()).tax_inclusive, true);
    assert.equal((await db.query("PRAGMA foreign_key_check")).length, 0);
    assert.equal((await db.query("SELECT version FROM schema_versions"))[0].version, VERSION);
  } finally { await db.close(); }
});

test("GST-EXCLUSIVE-04 migration failure rolls back dropped tables, data and version before a safe retry", async () => {
  const { tables } = await historical();
  const db = await v2Database(tables);
  const ledger = new Ledger(db, { now });
  const execute = db.exec;
  try {
    db.exec = async sql => {
      if (sql === "DROP TABLE sale_lines;") throw new Error("Simulated migration failure");
      return execute(sql);
    };
    await assert.rejects(ledger.initialize(menu.items, currentDefaults), /Simulated migration failure/);
    assert.equal((await db.query("SELECT version FROM schema_versions"))[0].version, 2);
    for (const name of Object.keys(V2_TABLES)) assert.deepEqual(await db.query(`SELECT * FROM ${name}`), tables[name], name);
    db.exec = execute;
    await ledger.initialize(menu.items, currentDefaults);
    assert.equal((await ledger.checkout(order())).total_paise, 17850);
  } finally { await db.close(); }
});

test("GST-EXCLUSIVE-05 v1/v2 backups remain restorable and mixed old/new bills reconcile in CSV/XLSX and full restore", async () => {
  const old = await historical();
  for (const version of [1, 2]) {
    const tables = project(old.tables, version === 1 ? LEGACY_TABLES : V2_TABLES);
    const payload = JSON.stringify({ format: "vgl-restaurant-backup", version, created_at: now(), tables, files: {} });
    const source = JSON.stringify({ payload, sha256: await digest(payload) });
    const inspected = await inspectBackup(source, () => database());
    assert.equal(inspected.version, VERSION);
    assert.equal(inspected.tables.sales[0].tax_inclusive, 1);
  }
  const { ledger, db } = await setup({ now });
  try {
    const original = await ledger.checkout(order());
    await ledger.saveSettings({ ...await ledger.settings(), tax_inclusive: false });
    const sale = await ledger.checkout(order({ payments: [
      { method: "cash", amount_paise: 7850, tendered_paise: 10000 },
      { method: "upi", amount_paise: 10000 },
    ] }));
    await ledger.adjust({ sale_id: sale.id, operation_id: "new-return", kind: "refund", amount_paise: 850, refunds: [{ method: "cash", amount_paise: 850 }], reason: "Partial return" });
    const report = await ledger.report(period);
    assert.equal(report.totals.sales_paise, 34850);
    assert.equal(report.totals.net_paise, 34000);
    const invoices = datasets(report)[0];
    const data = invoices.rows.map(row => Object.fromEntries(invoices.columns.map((column, index) => [column, row[index]])));
    assert.deepEqual(data.map(row => row["GST price basis"]), ["Included in menu price", "Added to menu price"]);
    assert.equal(data[1]["GST INR"], "8.50");
    assert.equal(data[1]["Taxable INR"], "170.00");
    const book = new ExcelJS.Workbook(); await book.xlsx.load(await xlsx(report));
    assert.equal(book.getWorksheet("Invoices").getCell("K3").value, 178.5);
    const backup = await createBackup(ledger, new MemoryImages());
    const before = await ledger.snapshot();
    await restoreBackup(backup, ledger, new MemoryImages(), () => database());
    assert.deepEqual(await ledger.snapshot(), before);
    assert.equal((await ledger.sale(original.id)).total_paise, 17000);
    const corrupt = JSON.parse(backup), invalid = JSON.parse(corrupt.payload);
    invalid.tables.sales[1].tax_inclusive = 1;
    corrupt.payload = JSON.stringify(invalid); corrupt.sha256 = await digest(corrupt.payload);
    await assert.rejects(inspectBackup(JSON.stringify(corrupt), () => database()));
    assert.deepEqual(await ledger.snapshot(), before);
    assert.deepEqual(Object.keys(before), Object.keys(TABLES));
    assert.equal(defaults.tax_inclusive, true);
  } finally { await db.close(); }
});
