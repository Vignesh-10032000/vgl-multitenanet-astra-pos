import test from "node:test";
import assert from "node:assert/strict";
import fc from "fast-check";

// The override is used only by the isolated mutation harness, never by the app.
const { quote, payments, payment, paise, decimal } = await import(
  process.env.RESTAURANT_DOMAIN_UNDER_TEST || "../../restaurant/domain.js"
);
const options = { seed: 20261031, numRuns: 1500 };
const line = fc.record({
  quantity: fc.integer({ min: 1, max: 9999 }),
  unit_paise: fc.integer({ min: 1, max: 1000000 }),
});
const cart = fc.array(line, { minLength: 1, maxLength: 8 }).chain((items) => {
  const gross = items.reduce((n, l) => n + l.quantity * l.unit_paise, 0);
  return fc.record({
    items: fc.constant(items),
    discount: fc.integer({ min: 0, max: gross }),
    rounded: fc.boolean(),
  });
});
const roundedDivision = (n, d) => {
  const whole = n / d;
  return Number(whole + (n % d >= (d + 1n) / 2n ? 1n : 0n));
};

test("PROP-01 independent integer oracle reconciles inclusive line GST, discounts and rounding", () => {
  fc.assert(fc.property(cart, ({ items, discount, rounded }) => {
    const settings = { receipt_mode: "tax_invoice", tax_bps: 500, round_rupee: rounded };
    const q = quote(items, discount, settings);
    assert.deepEqual(quote(items, discount, settings), q);
    const gross = items.reduce((n, l) => n + BigInt(l.quantity) * BigInt(l.unit_paise), 0n);
    const net = gross - BigInt(discount);
    assert.equal(q.gross_paise, Number(gross));
    assert.equal(q.total_paise, rounded ? roundedDivision(net, 100n) * 100 : Number(net));
    assert.equal(q.total_paise, q.taxable_paise + q.cgst_paise + q.sgst_paise + q.round_paise);
    assert.equal(q.lines.reduce((n, l) => n + l.discount_paise, 0), discount);
    let cumulative = 0n, allocated = 0n;
    for (const l of q.lines) {
      cumulative += BigInt(l.gross_paise);
      const next = BigInt(discount) * cumulative / gross;
      assert.equal(l.discount_paise, Number(next - allocated));
      allocated = next;
      assert.ok(l.net_paise >= 0);
      assert.equal(l.tax_paise, roundedDivision(BigInt(l.net_paise) * 5n, 105n));
      assert.equal(l.taxable_paise, l.net_paise - l.tax_paise);
      assert.equal(l.cgst_paise, Math.trunc(l.tax_paise / 2));
      assert.equal(l.sgst_paise, l.tax_paise - l.cgst_paise);
    }
    for (const field of ["tax_paise", "taxable_paise", "cgst_paise", "sgst_paise"])
      assert.equal(q[field], q.lines.reduce((n, l) => n + l[field], 0));
  }), options);
});

test("PROP-02 split receipts and cash change reconcile exactly at paise boundaries", () => {
  const split = fc.integer({ min: 2, max: 99999000000 }).chain((total) => fc.record({
    total: fc.constant(total),
    cash: fc.integer({ min: 1, max: total - 1 }),
    change: fc.integer({ min: 0, max: 1000000 }),
  }));
  fc.assert(fc.property(split, ({ total, cash, change }) => {
    const rows = payments(total, [
      { method: "cash", amount_paise: cash, tendered_paise: cash + change },
      { method: "upi", amount_paise: total - cash },
    ]);
    assert.equal(rows[0].amount_paise + rows[1].amount_paise, total);
    assert.equal(rows[0].change_paise, change);
    assert.equal(rows[1].change_paise, 0);
    assert.equal(rows[0].tendered_paise - rows[0].change_paise + rows[1].amount_paise, total);
    assert.throws(() => payments(total + 1, rows));
    assert.throws(() => payments(total, [rows[0], rows[0]]));
    assert.throws(() => payment(total, "cash", total - 1));
  }), options);
});

test("PROP-03 exact amount formatting round trips and invalid financial values fail closed", () => {
  fc.assert(fc.property(fc.integer({ min: 0, max: 99999999999 }), (n) => {
    assert.equal(paise(decimal(n)), n);
  }), options);
  fc.assert(fc.property(fc.constantFrom(NaN, Infinity, -Infinity, -1, 0, 1.5, "1", null, undefined), (quantity) => {
    assert.throws(() => quote([{ quantity, unit_paise: 17000 }]));
  }), options);
  for (const discount of [NaN, Infinity, -1, false, "", "0", 17001])
    assert.throws(() => quote([{ quantity: 1, unit_paise: 17000 }], discount));
  const high = quote([{ quantity: 1, unit_paise: 100000000000 }], 0, { receipt_mode: "tax_invoice", tax_bps: 500 });
  assert.equal(high.total_paise, 100000000000);
  assert.equal(high.tax_paise, roundedDivision(100000000000n * 5n, 105n));
  const simple = quote([{ quantity: 1, unit_paise: 10500 }], 0, { receipt_mode: "tax_invoice", tax_bps: 500 });
  assert.equal(simple.total_paise, 10500);
  assert.equal(simple.taxable_paise, 10000);
  assert.equal(simple.cgst_paise, 250);
  assert.equal(simple.sgst_paise, 250);
});
