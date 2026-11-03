import test from "node:test";
import assert from "node:assert/strict";
import { setup, menu, currentDefaults, order } from "./helpers.js";

test("STARTUP-01 current schema opens without a write transaction or reseeding", async () => {
  const { db, ledger } = await setup({ settings: currentDefaults });
  try {
    const sale = await ledger.checkout(order());
    const before = await ledger.snapshot();
    const originalBegin = db.begin;
    db.begin = () => { throw new Error("Warm initialization must not write"); };
    await ledger.initialize(menu.items, currentDefaults);
    db.begin = originalBegin;
    assert.deepEqual(await ledger.snapshot(), before);
    assert.equal((await ledger.sale(sale.id)).total_paise, 17850);
  } finally { await db.close(); }
});

test("STARTUP-02 future schema is rejected without modification", async () => {
  const { db, ledger } = await setup();
  try {
    await db.exec("UPDATE schema_versions SET version=999");
    const before = await ledger.snapshot();
    await assert.rejects(ledger.initialize(menu.items, currentDefaults), /newer app/);
    assert.deepEqual(await ledger.snapshot(), before);
  } finally { await db.close(); }
});
