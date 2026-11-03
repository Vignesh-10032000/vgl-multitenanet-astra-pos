import { test } from "node:test";
import assert from "node:assert/strict";
import { setup } from "./helpers.js";
import {
  billingQuote,
  billingPaymentPreview,
  checkoutInput,
  ledgerItems,
  menuProduct,
} from "../../restaurant/billing-adapter.js";

async function cartFor(ledger) {
  const p = (await ledger.products()).find((p) => p.id === "menu-001");
  return [{ product_id: p.id, quantity: "1.000", product: menuProduct(p) }];
}

test("converted controller contract preserves inclusive GST, string IDs and duplicate-submit ledger invariants", async () => {
  const { ledger, db } = await setup();
  try {
    const cart = await cartFor(ledger);
    const q = billingQuote(cart, "0.00", await ledger.settings());
    assert.equal(q.net_amount, "170.00");
    assert.equal(q.taxable_amount, "161.90");
    assert.equal(q.cgst_amount, "4.05");
    assert.equal(q.sgst_amount, "4.05");
    assert.deepEqual(
      billingPaymentPreview(q.net_amount, [
        { method: "CASH", amount: "200.00" },
      ]),
      { balance_due: "0.00", change_due: "30.00" },
    );
    const input = checkoutInput(cart, "0.00", "", crypto.randomUUID(), [
      { method: "CASH", amount: "200.00" },
    ]);
    const [a, b] = await Promise.all([
      ledger.checkout(input),
      ledger.checkout(input),
    ]);
    assert.equal(a.id, b.id);
    assert.equal(a.payment.amount_paise, 17000);
    assert.equal(a.payment.change_paise, 3000);
    assert.equal((await ledger.snapshot()).sales.length, 1);
    assert.equal(a.lines[0].product_id, "menu-001");
  } finally {
    await db.close();
  }
});

test("converted tender and portions reject unsupported, short, fractional and excess UPI inputs", () => {
  assert.throws(() => ledgerItems([{ quantity: "1.001", product: {} }]));
  assert.throws(() =>
    billingPaymentPreview("170.00", [{ method: "CASH", amount: "169.99" }]),
  );
  assert.throws(() =>
    billingPaymentPreview("170.00", [{ method: "UPI", amount: "200.00" }]),
  );
  assert.throws(() => checkoutInput([], "0", null, "op", [{ method: "CARD" }]));
  assert.throws(() => checkoutInput([], "0", null, "op", []));
  assert.deepEqual(
    billingPaymentPreview("170.00", [{ method: "UPI", amount: "170.00" }]),
    { balance_due: "0.00", change_due: "0.00" },
  );
});

test("local hold and recall transfer cart atomically and preferences survive a snapshot", async () => {
  const { ledger, db } = await setup();
  try {
    const cart = {
      cart: await cartFor(ledger),
      orderDiscount: "1.00",
      customerId: "",
      saleUuid: crypto.randomUUID(),
    };
    await ledger.saveDraft({ originalCart: cart.cart });
    const id = await ledger.holdCart(cart, "Table 4");
    assert.equal(await ledger.draft(), null);
    assert.equal((await ledger.heldBills())[0].label, "Table 4");
    assert.equal((await ledger.snapshot()).sales.length, 0);
    assert.deepEqual((await ledger.recallHeldBill(id)).cart, cart.cart);
    assert.deepEqual((await ledger.draft()).originalCart, cart.cart);
    assert.equal((await ledger.heldBills()).length, 0);
    await assert.rejects(ledger.recallHeldBill(id));
    await assert.rejects(ledger.discardHeldBill("cart"));
    await assert.rejects(ledger.holdCart({ cart: [] }, ""));
    await ledger.saveBillingPreference("quick-keys", [
      { key_number: 1, product_id: "menu-001" },
    ]);
    assert.equal(
      (await ledger.billingPreference("quick-keys"))[0].product_id,
      "menu-001",
    );
    assert.ok(
      (await ledger.snapshot()).drafts.some(
        (d) => d.id === "preference:quick-keys",
      ),
    );
  } finally {
    await db.close();
  }
});

test("HOLD-01 recall refuses to overwrite another durable active cart", async () => {
  const { ledger, db } = await setup();
  try {
    const cart = await cartFor(ledger);
    const id = await ledger.holdCart(
      { cart, saleUuid: "held-operation" },
      "Table 1",
    );
    await ledger.saveDraft({
      originalCart: cart,
      operation: "other-operation",
    });
    await assert.rejects(ledger.recallHeldBill(id), /active cart/i);
    assert.equal((await ledger.draft()).operation, "other-operation");
    assert.equal((await ledger.heldBills()).length, 1);
  } finally {
    await db.close();
  }
});
