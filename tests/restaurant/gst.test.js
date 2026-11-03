import test from "node:test";
import assert from "node:assert/strict";
import { Ledger } from "../../restaurant/repository.js";
import { quote, percent } from "../../restaurant/domain.js";
import { receiptHTML } from "../../restaurant/documents.js";
import { datasets, xlsx } from "../../restaurant/exports.js";
import {
  database,
  defaults,
  menu,
  setup,
  order,
  MemoryImages,
} from "./helpers.js";
import ExcelJS from "exceljs";

test("historical inclusive-GST fixture retains an exact 2.5 / 2.5 split", () => {
  assert.equal(defaults.gstin, "33BPFPD3960P2ZN");
  assert.equal(defaults.tax_confirmed, true);
  assert.equal(defaults.receipt_mode, "tax_invoice");
  assert.equal(defaults.tax_bps, 500);
  assert.equal(percent(500), "5");
  assert.equal(percent(500, 2), "2.5");
  assert.equal(percent(1, 2), "0.005");
  const q = quote([{ quantity: 1, unit_paise: 17000 }], 0, defaults);
  assert.equal(q.total_paise, 17000);
  assert.equal(q.taxable_paise, 16190);
  assert.equal(q.cgst_paise, 405);
  assert.equal(q.sgst_paise, 405);
  assert.equal(q.tax_paise, 810);
  assert.equal(q.taxable_paise + q.cgst_paise + q.sgst_paise, q.total_paise);
});

test("saved GST receipt prints document GSTIN and both 2.5 percent amounts without adding GST again", async () => {
  const { ledger, db } = await setup();
  try {
    const sale = await ledger.checkout(order());
    const html = await receiptHTML(sale, new MemoryImages());
    assert.match(html, /GSTIN: 33BPFPD3960P2ZN/);
    assert.match(html, /aria-label="Tax invoice"/);
    assert.match(html.replace(/<[^>]*>/g, ""), /CGST 2\.5%: ₹4\.05/);
    assert.match(html.replace(/<[^>]*>/g, ""), /SGST 2\.5%: ₹4\.05/);
    assert.equal(sale.lines[0].taxable_paise, 16190);
    assert.equal(sale.tax_paise, 810);
    assert.match(html, /<span>₹170\.00<\/span>/);
    assert.doesNotMatch(html, /TRAINING —/);
    assert.equal(sale.payment.amount_paise, 17000);
    assert.equal(sale.payment.change_paise, 3000);
  } finally {
    await db.close();
  }
});

test("GST configuration upgrades original training setup once without changing saved bills or store edits", async () => {
  const legacy = {
    ...defaults,
    gstin: "",
    receipt_mode: "training",
    tax_bps: 0,
    tax_confirmed: false,
    name: "Edited restaurant name",
  };
  delete legacy.gst_setup_revision;
  delete legacy.gst_confirmation_source;
  const db = database();
  const ledger = new Ledger(db);
  try {
    await ledger.initialize(menu.items, legacy);
    const old = await ledger.checkout(order());
    await ledger.initialize(menu.items, defaults);
    const updated = await ledger.settings();
    assert.equal(updated.gstin, defaults.gstin);
    assert.equal(updated.receipt_mode, "tax_invoice");
    assert.equal(updated.tax_bps, 500);
    assert.equal(updated.name, "Edited restaurant name");
    assert.deepEqual(await ledger.sale(old.id), old);
    assert.equal(old.tax_paise, 0);
    const next = await ledger.checkout(order());
    assert.equal(next.tax_paise, 810);
    assert.equal(next.total_paise, 17000);
    await ledger.saveSettings({ ...updated, receipt_mode: "bill_of_supply" });
    await ledger.initialize(menu.items, defaults);
    assert.equal((await ledger.settings()).receipt_mode, "bill_of_supply");
  } finally {
    await db.close();
  }
});

test("GST initialization preserves an already configured receipt/tax setup", async () => {
  const configured = {
    ...defaults,
    receipt_mode: "bill_of_supply",
    tax_bps: 0,
  };
  delete configured.gst_setup_revision;
  const db = database();
  const ledger = new Ledger(db);
  try {
    await ledger.initialize(menu.items, configured);
    await ledger.initialize(menu.items, defaults);
    assert.equal((await ledger.settings()).receipt_mode, "bill_of_supply");
  } finally {
    await db.close();
  }
});

test("auditor register retains snapshot GSTIN, taxable value and split GST in numeric XLSX cells", async () => {
  const { ledger, db } = await setup({ now: () => "2026-10-28T04:00:00.000Z" });
  try {
    const sale = await ledger.checkout(order());
    const settings = await ledger.settings();
    await ledger.saveSettings({ ...settings, receipt_mode: "bill_of_supply" });
    const r = await ledger.report({ from: "2026-10-01", to: "2026-10-31" });
    const invoices = datasets(r)[0];
    const row = Object.fromEntries(
      invoices.columns.map((name, i) => [name, invoices.rows[0][i]]),
    );
    assert.equal(row["Store GSTIN"], sale.identity.gstin);
    assert.equal(row["Taxable INR"], "161.90");
    assert.equal(row["CGST %"], "2.5");
    assert.equal(row["CGST INR"], "4.05");
    assert.equal(row["SGST INR"], "4.05");
    assert.equal(row["Total INR"], "170.00");
    const book = new ExcelJS.Workbook();
    await book.xlsx.load(await xlsx(r));
    const sheet = book.getWorksheet("Invoices");
    assert.equal(sheet.getCell("Q2").value, "33BPFPD3960P2ZN");
    assert.equal(sheet.getCell("T2").value, 4.05);
    assert.equal(sheet.getCell("V2").value, 4.05);
    assert.equal(sheet.getCell("K2").value, 170);
  } finally {
    await db.close();
  }
});
