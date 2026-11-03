import test from "node:test";
import assert from "node:assert/strict";
import { database, defaults, menu, order, setup, MemoryImages } from "./helpers.js";
import { SCHEMA, PAYMENT_SCHEMA, LEGACY_TABLES, VERSION } from "../../restaurant/schema.js";
import { Ledger } from "../../restaurant/repository.js";
import { createBackup, inspectBackup, restoreBackup } from "../../restaurant/backup.js";
import { digest } from "../../restaurant/assets.js";
import { datePreset } from "../../restaurant/report-dates.js";

function legacyTables(tables) {
  return Object.fromEntries(Object.entries(LEGACY_TABLES).map(([name, columns]) => [name,
    tables[name].map((row) => Object.fromEntries(columns.map((column) => [column,row[column]]))),
  ]));
}
async function historicalTables() {
  const { ledger, db } = await setup({ now: () => "2026-10-28T05:00:00.000Z" });
  try {
    const sale = await ledger.checkout(order());
    await ledger.adjust({ sale_id:sale.id,operation_id:"historic-return",kind:"refund",amount_paise:2000,reason:"Historical return" });
    return { tables: legacyTables(await ledger.snapshot()), sale };
  } finally { await db.close(); }
}

test("MIGRATION-01 version-1 SQLite preserves historical money, requests, corrections and final numbers", async () => {
  const { tables, sale } = await historicalTables();
  const db = database();
  try {
    const oldPayment = "CREATE TABLE IF NOT EXISTS payments(sale_id TEXT PRIMARY KEY REFERENCES sales(id), method TEXT NOT NULL, amount_paise INTEGER NOT NULL, tendered_paise INTEGER NOT NULL, change_paise INTEGER NOT NULL);";
    const schema = SCHEMA.replace(PAYMENT_SCHEMA,oldPayment).replace(/CREATE TABLE IF NOT EXISTS adjustment_payments[^;]+;/, "");
    await db.exec(schema);
    await db.run("INSERT INTO schema_versions VALUES(1)");
    for (const [name, columns] of Object.entries(LEGACY_TABLES)) for (const row of tables[name])
      await db.run(`INSERT INTO ${name}(${columns.join(",")}) VALUES(${columns.map(()=>"?").join(",")})`,columns.map((key)=>row[key]));
    const ledger = new Ledger(db);
    await ledger.initialize(menu.items,defaults);
    const snapshot=await ledger.snapshot();
    assert.deepEqual(legacyTables(snapshot),tables);
    assert.deepEqual(snapshot.adjustment_payments,[{adjustment_id:tables.adjustments[0].id,method:"cash",amount_paise:2000}]);
    assert.equal((await ledger.sale(sale.id)).payments[0].amount_paise,17000);
    assert.ok((await ledger.checkout(order())).bill_number.endsWith("000002"));
    await ledger.initialize(menu.items,defaults);
    assert.equal((await db.query("SELECT version FROM schema_versions"))[0].version,VERSION);
  } finally { await db.close(); }
});

test("MIGRATION-02 old backup and mixed-tender backup restore with images/settings/numbering intact", async () => {
  const old=await historicalTables();
  const payload=JSON.stringify({format:"vgl-restaurant-backup",version:1,created_at:"2026-10-28T05:00:00.000Z",tables:old.tables,files:{}});
  const source=JSON.stringify({sha256:await digest(payload),payload});
  const {ledger,db}=await setup();
  try {
    const images=new MemoryImages();
    await restoreBackup(source,ledger,images,()=>database());
    assert.equal((await ledger.report({from:"2026-10-01",to:"2026-10-31"})).totals.net_paise,15000);
    const request=order({payments:[{method:"cash",amount_paise:7000,tendered_paise:10000},{method:"upi",amount_paise:10000,tendered_paise:10000}]});
    const sale=await ledger.checkout(request);
    assert.ok(sale.bill_number.endsWith("000002"));
    const backup=await createBackup(ledger,images);
    const inspected=await inspectBackup(backup,()=>database());
    assert.equal(inspected.tables.payments.length,3);
    await restoreBackup(backup,ledger,images,()=>database());
    assert.equal((await ledger.sale(sale.id)).payments.length,2);
    const corrupt=JSON.parse(backup),data=JSON.parse(corrupt.payload);
    data.tables.payments.pop();corrupt.payload=JSON.stringify(data);corrupt.sha256=await digest(corrupt.payload);
    await assert.rejects(inspectBackup(JSON.stringify(corrupt),()=>database()),/shares|reconcile/i);
    assert.equal((await ledger.sale(sale.id)).payments.length,2);
  } finally { await db.close(); }
});

test("DATES-01 defaults and chips use Kolkata calendar days and Monday weeks across boundaries", () => {
  assert.deepEqual(datePreset("today","2026-10-30"),{from:"2026-10-30",to:"2026-10-30"});
  assert.deepEqual(datePreset("month","2026-10-30"),{from:"2026-10-01",to:"2026-10-30"});
  assert.deepEqual(datePreset("yesterday","2026-01-01"),{from:"2025-12-31",to:"2025-12-31"});
  assert.deepEqual(datePreset("week","2026-01-01"),{from:"2025-12-29",to:"2026-01-01"});
  assert.throws(()=>datePreset("today","2026-02-30"));
});
