import test from "node:test";
import assert from "node:assert/strict";
import {
  merchantPaymentUri,
  paymentQrAmount,
  paymentQrRequest,
} from "../../restaurant/upi-qr.js";

const merchant = {
  name: "Fixture restaurant",
  upi_id: "fixture@example",
  upi_payee: "Fixture & உணவகம்",
  upi_confirmed: true,
};
test("UPI-QR-01 verified destination and exact paise are URL encoded without parameter injection", () => {
  const uri = new URL(merchantPaymentUri(merchant, 17001, "operation123"));
  assert.equal(uri.protocol, "upi:");
  assert.equal(uri.host, "pay");
  assert.deepEqual(Object.fromEntries(uri.searchParams), {
    pa: "fixture@example",
    pn: merchant.upi_payee,
    am: "170.01",
    cu: "INR",
    tr: "operation123",
  });
  for (const invalid of [
    { ...merchant, upi_confirmed: false },
    { ...merchant, upi_id: "x@bank&pa=other@bank" },
    { ...merchant, upi_payee: "" },
  ])
    assert.throws(() => merchantPaymentUri(invalid, 17000), /merchant UPI/);
  for (const amount of [0, -1, 0.5, NaN])
    assert.throws(() => merchantPaymentUri(merchant, amount), /amount/);
});
test("UPI-QR-02 split requests only UPI share regardless of cash tender or change", () => {
  const rows = [
    { method: "CASH", amount: "200.00" },
    { method: "UPI", amount: "120.01" },
  ];
  assert.equal(paymentQrAmount("170.01", rows), 12001);
  const model = paymentQrRequest(merchant, "170.01", rows, "123-abc");
  assert.equal(model.demo, false);
  assert.equal(new URL(model.payload).searchParams.get("am"), "120.01");
  assert.equal(new URL(model.payload).searchParams.get("tr"), "123abc");
  assert.deepEqual(rows, [
    { method: "CASH", amount: "200.00" },
    { method: "UPI", amount: "120.01" },
  ]);
  for (const invalid of [
    [{ method: "UPI", amount: "0" }],
    [{ method: "UPI", amount: "171" }],
    [{ method: "UPI", amount: "50" }],
    [{ method: "CASH", amount: "170.01" }],
    [
      { method: "UPI", amount: "170.01" },
      { method: "UPI", amount: "170.01" },
    ],
  ])
    assert.throws(() => paymentQrAmount("170.01", invalid));
});
test("UPI-QR-03 missing/unverified settings produce explicitly non-payable demo text without changing settings", () => {
  for (const settings of [
    { name: "Fixture restaurant" },
    { ...merchant, upi_confirmed: false },
  ]) {
    const before = structuredClone(settings);
    const model = paymentQrRequest(
      settings,
      "170.00",
      [{ method: "UPI", amount: "170.00" }],
      "fixture-id",
    );
    assert.equal(model.demo, true);
    assert.equal(model.upi_id, "");
    assert.deepEqual(JSON.parse(model.payload), {
      format: "vgl-pos-qr-demo",
      payment: false,
      amount: "170.00",
      currency: "INR",
      reference: "fixtureid",
    });
    assert(!model.payload.includes("upi://"));
    assert(!model.payload.includes("fixture@example"));
    assert.deepEqual(settings, before);
  }
});
