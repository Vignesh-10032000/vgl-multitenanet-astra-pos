import test from "node:test";
import assert from "node:assert/strict";
import { fixedKgPortion, kilograms, portionKilograms } from "../../restaurant/product-options.js";
import { createBackup, restoreBackup } from "../../restaurant/backup.js";
import { setup, database, order, MemoryImages } from "./helpers.js";

test("fixed kilogram portions retain independent prices and legacy labels", () => {
  assert.equal(kilograms("00.500"), "0.5");
  assert.equal(kilograms("0.001"), "0.001");
  assert.equal(portionKilograms("1/2 kg"), "0.5");
  assert.equal(fixedKgPortion("0.500", "1/2 kg"), "1/2 kg");
  assert.equal(fixedKgPortion("1", "Standard"), "1 kg");
  assert.equal(fixedKgPortion("", "Full"), "Full");
  for (const value of ["0", "-1", "0.0001", "1e2", "10000", "NaN"])
    assert.throws(() => kilograms(value));
});

test("menu type and fixed kg price survive backup restore without changing saved sales", async () => {
  const source = await setup();
  const target = await setup();
  try {
    const before = await source.ledger.checkout(order());
    const original = (await source.ledger.products()).find(p => p.id === "menu-001");
    await source.ledger.saveProduct({ ...original, menu_type: "parcel", kilograms: "0.5", price_paise: 23000 });
    const p = (await source.ledger.products()).find(p => p.id === original.id);
    assert.equal(p.menu_type, "parcel");
    assert.equal(p.portion, "0.5 kg");
    assert.equal(p.price_paise, 23000);
    const newSale = await source.ledger.checkout(order({ items: [{ product_id: p.id, name: p.name, portion: p.portion, unit_paise: p.price_paise, quantity: 2 }], tendered_paise: 50000 }));
    assert.equal(newSale.gross_paise, 46000);
    await source.ledger.saveProduct({ ...p, price_paise: 25000 });
    assert.deepEqual(await source.ledger.sale(before.id), before);
    assert.deepEqual(await source.ledger.sale(newSale.id), newSale);
    const backup = await createBackup(source.ledger, new MemoryImages());
    await restoreBackup(backup, target.ledger, new MemoryImages(), async () => database());
    assert.deepEqual(await target.ledger.products(), await source.ledger.products());
    assert.deepEqual(await target.ledger.snapshot(), await source.ledger.snapshot());
  } finally { await source.db.close(); await target.db.close(); }
});

test("invalid menu assignment rolls back product edits and omitted assignment preserves choice", async () => {
  const { db, ledger } = await setup();
  try {
    const p = (await ledger.products()).find(p => p.id === "menu-001");
    assert.equal(p.menu_type, "regular");
    assert.equal((await ledger.products()).find(p => p.id === "menu-029").menu_type, "parcel");
    const before = await ledger.snapshot();
    await assert.rejects(ledger.saveProduct({ ...p, name: "Invalid edit", menu_type: "other" }));
    await assert.rejects(ledger.saveProduct({ ...p, kilograms: "0" }));
    assert.deepEqual(await ledger.snapshot(), before);
    await ledger.saveProduct({ ...p, menu_type: "parcel" });
    await ledger.saveProduct({ ...p, menu_type: undefined, name: "Renamed dish" });
    assert.equal((await ledger.products()).find(item => item.id === p.id).menu_type, "parcel");
  } finally { await db.close(); }
});
