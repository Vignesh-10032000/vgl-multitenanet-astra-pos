import test from "node:test";
import assert from "node:assert/strict";
import { setup, order } from "./helpers.js";
import { payments, paise } from "../../restaurant/domain.js";
import { controllerTenders } from "../../restaurant/billing-adapter.js";
import { datasets, xlsx } from "../../restaurant/exports.js";
import ExcelJS from "exceljs";

const period = { from: "2026-10-01", to: "2026-10-31" };
const split = () => order({ method: undefined, tendered_paise: undefined, payments: [
  { method: "cash", amount_paise: 7000, tendered_paise: 10000 },
  { method: "upi", amount_paise: 10000, tendered_paise: 10000 },
] });

test("SPLIT-01 mixed tender commits once, preserves GST and filters actual payment shares", async () => {
  const { ledger, db } = await setup({ now: () => "2026-10-30T04:00:00.000Z" });
  try {
    const request = split();
    const [sale, retry] = await Promise.all([ledger.checkout(request), ledger.checkout(request)]);
    assert.equal(sale.id, retry.id);
    assert.equal(sale.payments.length, 2);
    assert.equal(sale.total_paise, 17000);
    assert.equal(sale.tax_paise, 810);
    assert.equal(sale.payments[0].change_paise, 3000);
    assert.equal((await ledger.snapshot()).sales.length, 1);
    for (const [method, expected] of [["all", 17000], ["cash", 7000], ["upi", 10000]]) {
      const r = await ledger.report({ ...period, method });
      assert.equal(r.invoices.length, 1);
      assert.equal(r.lines.length, 1);
      assert.equal(r.totals.net_paise, expected);
      assert.equal(r.totals.cash_paise + r.totals.upi_paise, expected);
      assert.equal(r.daily[0].net_paise, expected);
    }
  } finally { await db.close(); }
});

test("SPLIT-02 failure on second tender rolls back the entire bill and final number", async () => {
  const { ledger, db } = await setup();
  try {
    await db.exec("CREATE TRIGGER fail_second BEFORE INSERT ON payments WHEN NEW.method='upi' BEGIN SELECT RAISE(ABORT,'second tender failed'); END;");
    await assert.rejects(ledger.checkout(split()), /second tender/);
    for (const table of ["sales", "sale_lines", "payments", "sequences"])
      assert.equal((await db.query(`SELECT COUNT(*) n FROM ${table}`))[0].n, 0);
  } finally { await db.close(); }
});

test("SPLIT-03 returned payment channels reconcile and a changed retry is rejected", async () => {
  const { ledger, db } = await setup({ now: () => "2026-10-30T04:00:00.000Z" });
  try {
    const sale = await ledger.checkout(split());
    await assert.rejects(ledger.adjust({ sale_id: sale.id, operation_id: "missing-channels", kind: "refund", amount_paise: 5000, reason: "Partial return" }), /return amounts/i);
    const input = { sale_id: sale.id, operation_id: "return", kind: "refund", amount_paise: 5000, reason: "Partial return", refunds: [{ method: "cash", amount_paise: 2000 }, { method: "upi", amount_paise: 3000 }] };
    await ledger.adjust(input);
    await ledger.adjust(input);
    await assert.rejects(ledger.adjust({ ...input, refunds: [{ method: "cash", amount_paise: 5000 }] }), /identifier/);
    const r = await ledger.report(period);
    assert.equal(r.totals.sales_paise - r.totals.corrections_paise, r.totals.net_paise);
    assert.equal(r.totals.net_paise, 12000);
    assert.equal(r.totals.cash_paise, 5000);
    assert.equal(r.totals.upi_paise, 7000);
  } finally { await db.close(); }
});

test("SPLIT-04 zero-total and zero-share tenders cannot create phantom mixed bills", () => {
  assert.throws(() => payments(0, [
    { method: "cash", amount_paise: 0 }, { method: "upi", amount_paise: 0 },
  ]), /one payment/);
  assert.throws(() => payments(100, [
    { method: "cash", amount_paise: 100 }, { method: "upi", amount_paise: 0 },
  ]), /Payment share/);
  for (const [total, cash, upi, method] of [
    ["0.00", "0.00", "0.00", "cash"],
    ["1.00", "1.00", "0.00", "cash"],
    ["1.00", "0.00", "1.00", "upi"],
  ]) {
    const result = controllerTenders(total, [{ method: "CASH", amount: cash }, { method: "UPI", amount: upi }]);
    assert.equal(result.length, 1);
    assert.equal(result[0].method, method);
    assert.equal(result[0].amount_paise, paise(total));
  }
});

test("SPLIT-05 filtered multi-line exports reconcile selected shares including round-off and returns", async () => {
  const { ledger, db } = await setup({ now: () => "2026-10-30T04:00:00.000Z" });
  try {
    await ledger.saveSettings({ ...await ledger.settings(), round_rupee: true });
    const item = (await ledger.products()).find((p) => p.id === "menu-002");
    const sale = await ledger.checkout(order({
      items: [
        ...order().items,
        { product_id: item.id, name: item.name, portion: item.portion, unit_paise: item.price_paise, quantity: 1 },
      ],
      discount_paise: 51,
      payments: [
        { method: "cash", amount_paise: 10001, tendered_paise: 15000 },
        { method: "upi", amount_paise: 17000 + item.price_paise - 100 - 10001 },
      ],
    }));
    await ledger.adjust({ sale_id: sale.id, operation_id: "actual-return", kind: "refund", amount_paise: 305, reason: "Actual channels", refunds: [{ method: "cash", amount_paise: 101 }, { method: "upi", amount_paise: 204 }] });
    const historical = await ledger.sale(sale.id);
    for (const method of ["all", "cash", "upi"]) {
      const report = await ledger.report({ ...period, method });
      const tables = datasets(report);
      for (const name of ["Invoices", "Items", "Item sales"]) {
        const table = tables.find((t) => t.name === name);
        const column = table.columns.indexOf("Selected payment INR");
        assert.notEqual(column, -1);
        assert.equal(table.rows.reduce((sum, row) => sum + paise(row[column]), 0), report.totals.sales_paise);
      }
      assert.equal(report.invoices.length, 1);
      assert.equal(report.lines.length, 2);
      const correction = tables.find((t) => t.name === "Corrections");
      assert.equal(paise(correction.rows[0][correction.columns.indexOf("Selected payment INR")]), report.totals.corrections_paise);
      const workbook = new ExcelJS.Workbook();
      await workbook.xlsx.load(await xlsx(report));
      const sheet = workbook.getWorksheet("Items");
      const column = tables.find((t) => t.name === "Items").columns.indexOf("Selected payment INR") + 1;
      assert.equal(sheet.rowCount, 3);
      assert.equal(sheet.getCell(2, column).type, ExcelJS.ValueType.Number);
      assert.equal(report.totals.sales_paise - report.totals.corrections_paise, report.totals.net_paise);
    }
    assert.deepEqual(await ledger.sale(sale.id), historical);
  } finally { await db.close(); }
});
