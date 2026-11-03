import { metricText } from "../../restaurant/labels.js";
import test from "node:test";
import assert from "node:assert/strict";
import {
  createBackup,
  inspectBackup,
  restoreBackup,
} from "../../restaurant/backup.js";
import {
  csv,
  xlsx,
  spreadsheetText,
  datasets,
} from "../../restaurant/exports.js";
import { digest } from "../../restaurant/assets.js";
import { setup, order, database, MemoryImages } from "./helpers.js";
import ExcelJS from "exceljs";

test("CSV keeps negative monetary amounts numeric while protecting formula text", () => {
  const source = csv({
    from: "2026-10-01",
    to: "2026-10-31",
    method: "all",
    invoices: [],
    lines: [],
    daily: [],
    items: [],
    adjustments: [],
    prints: [],
    totals: { round_paise: -49 },
  });
  assert.ok(source.includes(`"${metricText("round_paise")}","-0.49"`));
  assert.ok(!source.includes("'-0.49"));
});

test("a fully discounted void remains marked as a correction despite a zero amount", async () => {
  const { db, ledger } = await setup({ now: () => "2026-10-28T03:00:00.000Z" });
  const sale = await ledger.checkout(
    order({ discount_paise: 17000, tendered_paise: 0 }),
  );
  await ledger.adjust({
    sale_id: sale.id,
    operation_id: "zero-void",
    kind: "void",
    amount_paise: 0,
    reason: "Cancelled complimentary order",
  });
  const r = await ledger.report({ from: "2026-10-01", to: "2026-10-31" });
  assert.equal(r.invoices[0].correction_count, 1);
  assert.equal(datasets(r)[0].rows[0][13], "Correction recorded");
  await db.close();
});

test("complete backup restores settings, images, snapshots, corrections, draft and numbering", async () => {
  const { db, ledger } = await setup({ now: () => "2026-10-28T03:00:00.000Z" });
  const images = new MemoryImages();
  const path = await images.put("data:image/jpeg;base64,SGVsbG8=");
  const p = (await ledger.products())[0];
  await ledger.saveProduct({ ...p, image: path });
  await ledger.saveSettings({ ...(await ledger.settings()), logo: path });
  const sale = await ledger.checkout(order());
  await ledger.adjust({
    sale_id: sale.id,
    operation_id: "refund",
    kind: "refund",
    amount_paise: 2000,
    reason: "Test refund",
  });
  await ledger.printAttempt(sale.id, "failed", "USB unavailable");
  await ledger.saveDraft({ items: [], operation: "draft" });
  const source = await createBackup(ledger, images);
  const target = await setup();
  const restoredImages = new MemoryImages();
  await restoreBackup(source, target.ledger, restoredImages, async () =>
    database(),
  );
  assert.deepEqual(await target.ledger.snapshot(), await ledger.snapshot());
  assert.equal(await restoredImages.read(path), await images.read(path));
  const next = await target.ledger.checkout(order());
  assert.ok(next.bill_number.endsWith("000002"));
  assert.equal(
    (await target.ledger.sale(sale.id)).adjustments[0].reason,
    "Test refund",
  );
  await db.close();
  await target.db.close();
});
test("truncated, modified, missing-image and internally inconsistent backups preserve active ledger", async () => {
  const { db, ledger } = await setup();
  const images = new MemoryImages();
  await ledger.checkout(order());
  const source = await createBackup(ledger, images);
  const before = await ledger.snapshot();
  await assert.rejects(
    restoreBackup(source.slice(0, -1), ledger, images, async () => database()),
  );
  const envelope = JSON.parse(source);
  const payload = JSON.parse(envelope.payload);
  payload.tables.payments[0].amount_paise = 1;
  const changed = JSON.stringify(payload);
  await assert.rejects(
    restoreBackup(
      JSON.stringify({ payload: changed, sha256: await digest(changed) }),
      ledger,
      images,
      async () => database(),
    ),
    /CHECK|reconcile/,
  );
  const missing = JSON.parse(envelope.payload);
  missing.tables.products[0].image = "images/" + "a".repeat(64) + ".jpg";
  const bad = JSON.stringify(missing);
  await assert.rejects(
    inspectBackup(
      JSON.stringify({ payload: bad, sha256: await digest(bad) }),
      async () => database(),
    ),
    /image/,
  );
  assert.deepEqual(await ledger.snapshot(), before);
  await db.close();
});
test("CSV quoting/formula protection and XLSX real parser retain Tamil, exact money and matching totals", async () => {
  const { db, ledger } = await setup({ now: () => "2026-10-28T03:00:00.000Z" });
  const customer = await ledger.saveCustomer({
    name: '=SUM(1,2) "பிரியா"\nசோதனை',
    phone: "123",
    city: "Pollachi",
  });
  await ledger.checkout(order({ customer_id: customer.id }));
  const r = await ledger.report({ from: "2026-10-01", to: "2026-10-31" });
  const data = csv(r);
  assert.ok(data.startsWith("\uFEFF"));
  assert.ok(data.includes("'=SUM(1,2) " + '""பிரியா""'));
  assert.ok(data.includes("170.00"));
  assert.equal(spreadsheetText(" \t@evil"), "' \t@evil");
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.load(await xlsx(r));
  assert.equal(workbook.worksheets.length, 9);
  assert.equal(workbook.getWorksheet("Invoices").getCell("K2").value, 170);
  assert.equal(
    workbook.getWorksheet("Invoices").getCell("C2").type,
    ExcelJS.ValueType.String,
  );
  assert.equal(
    workbook.getWorksheet("Invoices").getCell("C2").value,
    '\'=SUM(1,2) "பிரியா"\nசோதனை',
  );
  const summary = workbook.getWorksheet("Summary");
  let salesTotal;
  summary.eachRow((row) => {
    if (row.getCell(1).value === metricText("sales_paise"))
      salesTotal = row.getCell(2).value;
  });
  assert.equal(salesTotal, 170);
  const tables = datasets(r);
  assert.equal(tables.find((t) => t.name === "Daily").rows[0][4], "170.00");
  await db.close();
});
