import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setup, order, database, defaults, menu } from "./helpers.js";
import { Ledger } from "../../restaurant/repository.js";
const period = { from: "2026-10-01", to: "2026-10-31" };
test("atomic checkout survives reopening a real SQLite file with final number and snapshots", async () => {
  const dir = mkdtempSync(join(tmpdir(), "restaurant-"));
  const path = join(dir, "test.sqlite");
  try {
    const { db, ledger } = await setup({
      path,
      now: () => "2026-10-28T03:00:00.000Z",
    });
    const sale = await ledger.checkout(order());
    assert.equal(sale.bill_number, "AR/2627/000001");
    assert.equal(sale.payment.change_paise, 3000);
    await db.close();
    const reopened = new Ledger(database(path));
    await reopened.initialize(menu.items, defaults);
    assert.equal((await reopened.sale(sale.id)).total_paise, 17000);
    assert.equal((await reopened.products()).length, 36);
    await reopened.db.close();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
test("concurrent retries save one sale and reject a different request using the same operation", async () => {
  const { db, ledger } = await setup();
  const request = order();
  const results = await Promise.all(
    Array.from({ length: 12 }, () => ledger.checkout(request)),
  );
  assert.equal(new Set(results.map((s) => s.id)).size, 1);
  for (const t of ["sales", "payments", "sale_lines"])
    assert.equal((await db.query(`SELECT COUNT(*) AS n FROM ${t}`))[0].n, 1);
  await assert.rejects(
    ledger.checkout({ ...request, tendered_paise: 30000 }),
    /different bill/,
  );
  await db.close();
});
test("injected payment failure rolls back number, sale, items, payment and draft deletion", async () => {
  const { db, ledger } = await setup();
  await ledger.saveDraft({ items: ["not-yet-saved"] });
  await db.exec(
    "CREATE TRIGGER test_payment_failure BEFORE INSERT ON payments BEGIN SELECT RAISE(ABORT,'injected payment failure'); END;",
  );
  const request = order();
  await assert.rejects(ledger.checkout(request), /injected/);
  for (const t of ["sales", "sale_lines", "payments", "sequences"])
    assert.equal((await db.query(`SELECT COUNT(*) AS n FROM ${t}`))[0].n, 0);
  assert.deepEqual(await ledger.draft(), { items: ["not-yet-saved"] });
  await db.exec("DROP TRIGGER test_payment_failure");
  const sale = await ledger.checkout(request);
  assert.ok(sale.bill_number.endsWith("000001"));
  assert.equal(await ledger.draft(), null);
  await db.close();
});
test("product edits and customer edits cannot rewrite saved bill snapshots; inactive menu rejected", async () => {
  const { db, ledger } = await setup();
  const c = await ledger.saveCustomer({
    name: "பிரியா",
    phone: "99999",
    city: "Pollachi",
  });
  const sale = await ledger.checkout(order({ customer_id: c.id }));
  const product = (await ledger.products()).find((p) => p.id === "menu-001");
  await ledger.saveProduct({
    ...product,
    name: "New name",
    price_paise: 99999,
    active: false,
  });
  await ledger.saveCustomer({ ...c, name: "Changed customer" });
  const saved = await ledger.sale(sale.id);
  assert.equal(saved.lines[0].name, "CHICKEN BIRIYANI");
  assert.equal(saved.lines[0].unit_paise, 17000);
  assert.equal(saved.customer.name, "பிரியா");
  await assert.rejects(ledger.checkout(order()), /inactive/);
  await ledger.saveProduct({ ...product, price_paise: 18000 });
  await assert.rejects(ledger.checkout(order()), /Menu changed/);
  await db.close();
});
test("more than 500 independent bills; printing failures and reprints never add revenue", async () => {
  const { db, ledger } = await setup({ now: () => "2026-10-28T03:00:00.000Z" });
  const sales = [];
  for (let i = 0; i < 510; i++) sales.push(await ledger.checkout(order()));
  const attempt = await ledger.printAttempt(sales[0].id);
  await ledger.printAttempt(sales[0].id, "failed", "Printer offline", attempt);
  await ledger.printAttempt(sales[0].id, "submitted", "Paper unconfirmed");
  const r = await ledger.report(period);
  assert.equal(r.totals.bills, 510);
  assert.equal(r.totals.sales_paise, 8670000);
  assert.equal(r.prints.length, 2);
  assert.equal(
    (await db.query("SELECT last_number FROM sequences"))[0].last_number,
    510,
  );
  await db.close();
});
test("date/payment filters, cross-month refunds, and voids reconcile by event date", async () => {
  let now = "2026-09-30T18:29:59.999Z";
  const { db, ledger } = await setup({ now: () => now });
  const prior = await ledger.checkout(order());
  now = "2026-09-30T18:30:00.000Z";
  const cash = await ledger.checkout(order());
  const upi = await ledger.checkout(
    order({ method: "upi", tendered_paise: 17000 }),
  );
  await ledger.adjust({
    sale_id: prior.id,
    operation_id: "refund-prior",
    kind: "refund",
    amount_paise: 3000,
    reason: "Returned payment",
  });
  await ledger.adjust({
    sale_id: upi.id,
    operation_id: "void-upi",
    kind: "void",
    amount_paise: 17000,
    reason: "Duplicate customer order",
  });
  await assert.rejects(
    ledger.adjust({
      sale_id: upi.id,
      operation_id: "again",
      kind: "refund",
      amount_paise: 1,
      reason: "test",
    }),
    /corrected/,
  );
  const all = await ledger.report(period),
    cashOnly = await ledger.report({ ...period, method: "cash" }),
    upiOnly = await ledger.report({ ...period, method: "upi" });
  assert.equal(all.invoices.length, 2);
  assert.equal(all.adjustments.length, 2);
  assert.equal(all.totals.net_paise, 14000);
  assert.equal(cashOnly.totals.net_paise, 14000);
  assert.equal(upiOnly.totals.net_paise, 0);
  assert.equal(all.daily[0].net_paise, 14000);
  assert.equal(cash.total_paise, 17000);
  await db.close();
});
test("financial-year series resets safely; void numbers stay consumed", async () => {
  let now = "2026-03-31T18:29:59.999Z";
  const { db, ledger } = await setup({ now: () => now });
  const old = await ledger.checkout(order());
  await ledger.adjust({
    sale_id: old.id,
    operation_id: "void",
    kind: "void",
    amount_paise: 17000,
    reason: "Wrong order",
  });
  const next = await ledger.checkout(order());
  assert.ok(next.bill_number.endsWith("000002"));
  now = "2026-03-31T18:30:00.000Z";
  const fresh = await ledger.checkout(order());
  assert.equal(fresh.bill_number, "AR/2627/000001");
  assert.equal(old.fy, "2025-26");
  await db.close();
});
test("unconfirmed current tax status and invalid products/customers fail before persistence", async () => {
  const { db, ledger } = await setup();
  await assert.rejects(
    ledger.saveSettings({
      ...defaults,
      receipt_mode: "bill_of_supply",
      tax_confirmed: false,
    }),
    /Confirm current/,
  );
  await assert.rejects(
    ledger.saveProduct({
      name: "",
      portion: "full",
      category: "Menu",
      price_paise: 100,
      active: true,
    }),
    /Name/,
  );
  await assert.rejects(ledger.saveCustomer({ name: "" }), /Name/);
  assert.equal((await ledger.settings()).receipt_mode, defaults.receipt_mode);
  await db.close();
});
