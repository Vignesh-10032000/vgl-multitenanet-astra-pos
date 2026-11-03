import test from "node:test";
import assert from "node:assert/strict";
import {
  paise,
  decimal,
  quote,
  payment,
  dayAt,
  financialYear,
  dateBounds,
  billNumber,
  operationId,
} from "../../restaurant/domain.js";
import { menu } from "./helpers.js";

test("exact paise parsing rejects fractional paise, exponents and nonfinite input", () => {
  assert.equal(paise("170.01"), 17001);
  assert.equal(decimal(-30), "-0.30");
  for (const bad of ["0.001", "NaN", "Infinity", "1e2", "-1", "1,000", ""])
    assert.throws(() => paise(bad));
});
test("independent photographed menu portions retain 450 / 230 prices", () => {
  const items = menu.items.filter(
    (i) =>
      i.source_label.includes("MUTTON") &&
      i.category.toLowerCase().includes("parcel"),
  );
  const prices = items.map((i) => i.price_paise);
  assert.ok(prices.includes(45000));
  assert.ok(prices.includes(23000));
  assert.equal(menu.items.length, 36);
});
test("cash tender is separate from revenue; GPay stores UPI", () => {
  assert.deepEqual(payment(17000, "cash", 20000), {
    method: "cash",
    amount_paise: 17000,
    tendered_paise: 20000,
    change_paise: 3000,
  });
  assert.equal(payment(17000, "upi", 999999).tendered_paise, 17000);
  assert.throws(() => payment(17000, "cash", 16999));
  assert.throws(() => payment(17000, "card", 17000));
});
test("discount allocations, included GST and rupee round-off reconcile exactly", () => {
  const q = quote(
    [
      { unit_paise: 17001, quantity: 1 },
      { unit_paise: 23000, quantity: 2 },
    ],
    101,
    { receipt_mode: "tax_invoice", tax_bps: 500, round_rupee: true },
  );
  assert.equal(q.gross_paise, 63001);
  assert.equal(q.discount_paise, 101);
  assert.equal(q.total_paise, 62900);
  assert.equal(
    q.lines.reduce((n, l) => n + l.discount_paise, 0),
    101,
  );
  for (const l of q.lines) {
    assert.equal(l.cgst_paise + l.sgst_paise, l.tax_paise);
    assert.equal(l.taxable_paise + l.tax_paise, l.net_paise);
  }
  assert.equal(
    quote([{ unit_paise: 10500, quantity: 1 }], 0, {
      receipt_mode: "tax_invoice",
      tax_bps: 500,
    }).tax_paise,
    500,
  );
  assert.equal(
    quote([{ unit_paise: 17000, quantity: 1 }], 0, {
      receipt_mode: "bill_of_supply",
    }).tax_paise,
    0,
  );
  assert.equal(
    quote([{ unit_paise: 149, quantity: 1 }], 0, { round_rupee: true })
      .round_paise,
    -49,
  );
});
test("invalid quantities, discounts and overflow are rejected", () => {
  for (const q of [0, -1, 1.5, 10000])
    assert.throws(() => quote([{ unit_paise: 17000, quantity: q }]));
  assert.throws(() => quote([{ unit_paise: 100, quantity: 1 }], 101));
  assert.throws(() => quote([{ unit_paise: 100000000000, quantity: 9999 }]));
});
test("Kolkata boundaries are inclusive through exclusive next-day and FY rolls April 1", () => {
  assert.equal(dayAt("2026-03-31T18:29:59.999Z"), "2026-03-31");
  assert.equal(dayAt("2026-03-31T18:30:00.000Z"), "2026-04-01");
  assert.equal(financialYear("2026-03-31T18:29:59.999Z"), "2025-26");
  assert.equal(financialYear("2026-03-31T18:30:00.000Z"), "2026-27");
  assert.deepEqual(dateBounds("2026-10-01", "2026-10-31"), [
    "2026-09-30T18:30:00.000Z",
    "2026-10-31T18:30:00.000Z",
  ]);
  assert.throws(() => dateBounds("2026-02-30", "2026-03-01"));
});
test("bill numbers fit sixteen characters and secure identifiers do not need modern WebView helpers", () => {
  assert.equal(billNumber("AR", "2026-27", 1), "AR/2627/000001");
  assert.equal(billNumber("ABCD", "2026-27", 999999).length, 16);
  assert.throws(() => billNumber("AR", "2026-27", 1000000));
  assert.throws(() => billNumber("ABCDE", "2026-27", 1));
  const ids = Array.from({ length: 100 }, operationId);
  assert.equal(new Set(ids).size, 100);
  assert.match(
    ids[0],
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
});
