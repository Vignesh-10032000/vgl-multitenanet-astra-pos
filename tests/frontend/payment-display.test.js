import test from "node:test";
import assert from "node:assert/strict";
import { paymentSummary } from "../../src/vglpos/web/static/src/js/payment-display.js";

test("PAY-01 distinguishes exact, short and excess tender without rounding drift", () => {
  assert.deepEqual(paymentSummary("213.00", [{ amount: "213.00" }]), { received: "213.00", balance: "0.00", change: "0.00" });
  assert.deepEqual(paymentSummary("213.00", [{ amount: "200.00" }]), { received: "200.00", balance: "13.00", change: "0.00" });
  assert.deepEqual(paymentSummary("213.00", [{ amount: "500.00" }]), { received: "500.00", balance: "0.00", change: "287.00" });
  assert.deepEqual(paymentSummary("0.30", [{ amount: "0.10" }, { amount: "0.20" }]), { received: "0.30", balance: "0.00", change: "0.00" });
});

test("PAY-02 invalid tender cannot produce a misleading paid state", () => {
  for (const amount of ["-1", "1e3", "1.234", "abc", "Infinity"]) assert.throws(() => paymentSummary("213.00", [{ amount }]));
  assert.equal(paymentSummary("213.00", [{ amount: "" }]).balance, "213.00");
});
