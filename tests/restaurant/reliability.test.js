import test from "node:test";
import assert from "node:assert/strict";
import fc from "fast-check";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { setup, database, defaults, menu, order, MemoryImages } from "./helpers.js";
import { Ledger } from "../../restaurant/repository.js";
import { createBackup, restoreBackup, inspectBackup } from "../../restaurant/backup.js";
import { digest } from "../../restaurant/assets.js";
import { TABLES } from "../../restaurant/schema.js";
import { OwnerAccess, ACCESS_KEY } from "../../restaurant/access.js";
import { PersistentBackups } from "../../restaurant/backup-service.js";

test("AUDIT-01 invalid discount cannot silently become zero in a completed financial record", async () => {
  const { ledger, db } = await setup();
  try {
    const before = await ledger.snapshot();
    for (const discount_paise of [NaN, false, "", Infinity, -1, "0"])
      await assert.rejects(ledger.checkout(order({ discount_paise })), /Discount/);
    assert.deepEqual(await ledger.snapshot(), before);
    const sale = await ledger.checkout(order({ discount_paise: undefined }));
    assert.equal(sale.discount_paise, 0);
  } finally { await db.close(); }
});

test("SQLITE-01 every checkout mutation and pre-commit failure restores the exact prior state", async () => {
  // Sequence, sale, two lines, two tenders, draft deletion, commit.
  for (let failAt = 1; failAt <= 8; failAt++) {
    const { ledger, db } = await setup();
    try {
      await ledger.checkout(order());
      await ledger.saveDraft({ originalCart: ["preserve"], operation: "draft" });
      const before = await ledger.snapshot();
      let writes = 0;
      const run = db.run, commit = db.commit;
      db.run = async (...args) => {
        if (++writes === failAt) throw new Error("injected write failure");
        return run(...args);
      };
      db.commit = async () => {
        if (++writes === failAt) throw new Error("injected commit failure");
        return commit();
      };
      const p = (await ledger.products()).find((p) => p.id === "menu-002");
      const input = order({ items: [...order().items, {
        product_id: p.id, name: p.name, portion: p.portion, unit_paise: p.price_paise, quantity: 1,
      }], payments: [{ method: "cash", amount_paise: 100 }, { method: "upi", amount_paise: 16900 + p.price_paise }] });
      await assert.rejects(ledger.checkout(input), /injected/);
      db.run = run; db.commit = commit;
      assert.deepEqual(await ledger.snapshot(), before, `failure step ${failAt}`);
      const saved = await ledger.checkout(input);
      assert.ok(saved.bill_number.endsWith("000002"));
      assert.equal((await ledger.checkout(input)).id, saved.id);
      assert.deepEqual(await db.query("PRAGMA foreign_key_check"), []);
      assert.equal((await db.query("PRAGMA integrity_check"))[0].integrity_check, "ok");
    } finally { await db.close(); }
  }
});

test("SQLITE-02 interleaved service reads see complete bills and constraints reject duplicates/orphans", async () => {
  const { ledger, db } = await setup();
  try {
    const work = [];
    for (let i = 0; i < 25; i++) {
      work.push(ledger.checkout(order()));
      work.push(ledger.snapshot().then((s) => {
        assert.equal(s.sales.length, s.sale_lines.length);
        assert.equal(s.sales.length, s.payments.length);
        return null;
      }));
    }
    const results = (await Promise.all(work)).filter(Boolean);
    assert.equal(new Set(results.map((s) => s.bill_number)).size, 25);
    const snapshot = await ledger.snapshot();
    const sale = snapshot.sales[0];
    for (const overrides of [
      { operation_id: "different-op", sequence_number: 900, bill_number: sale.bill_number },
      { operation_id: sale.operation_id, sequence_number: 901, bill_number: "different-number" },
      { operation_id: "different-op", bill_number: "different-number" },
    ]) await assert.rejects(ledger.transaction(() => ledger.insert("sales", { ...sale, id: crypto.randomUUID(), ...overrides })), /UNIQUE/);
    await assert.rejects(ledger.transaction(() => ledger.insert("payments", { ...snapshot.payments[0], sale_id: "missing" })), /FOREIGN KEY/);
    assert.deepEqual(await ledger.snapshot(), snapshot);
  } finally { await db.close(); }
});

test("PROP-SQLITE-03 generated retries preserve historical lines after menu edits", async () => {
  await fc.assert(fc.asyncProperty(fc.integer({ min: 1, max: 9999 }), fc.integer({ min: 0, max: 17000 }), async (quantity, discount_paise) => {
    const { ledger, db } = await setup();
    try {
      const input = order({ items: [{ ...order().items[0], quantity }], discount_paise, method: "upi" });
      const [sale, retry] = await Promise.all([ledger.checkout(input), ledger.checkout(input)]);
      assert.equal(retry.id, sale.id);
      assert.equal(sale.total_paise, quantity * 17000 - discount_paise);
      const product = (await ledger.products()).find((p) => p.id === "menu-001");
      await ledger.saveProduct({ ...product, name: "Changed", price_paise: 1, active: false });
      assert.deepEqual(await ledger.sale(sale.id), sale);
      assert.equal((await ledger.checkout(input)).id, sale.id);
      assert.equal((await ledger.snapshot()).sales.length, 1);
    } finally { await db.close(); }
  }), { seed: 20261031, numRuns: 60 });
});

test("SQLITE-04 holds and draft operations recover across file reopen without completing sales", async () => {
  const directory = await mkdtemp(join(tmpdir(), "pos-audit-"));
  let db;
  try {
    ({ db } = await setup({ path: join(directory, "fixture.sqlite") }));
    let ledger = new Ledger(db);
    const cart = { cart: [{ product_id: "menu-001", quantity: 2 }], saleUuid: "held-op", orderDiscount: 101, customerId: null };
    await ledger.saveDraft({ originalCart: cart.cart, operation: cart.saleUuid });
    const id = await ledger.holdCart(cart, "Table test");
    await db.close(); db = database(join(directory, "fixture.sqlite"));
    ledger = new Ledger(db); await ledger.initialize(menu.items, defaults);
    assert.equal((await ledger.heldBills()).length, 1);
    assert.equal(await ledger.draft(), null);
    const recall = await ledger.recallHeldBill(id);
    assert.deepEqual(recall.cart, cart.cart);
    await db.close(); db = database(join(directory, "fixture.sqlite"));
    ledger = new Ledger(db);
    assert.deepEqual((await ledger.draft()).originalCart, cart.cart);
    assert.equal((await ledger.heldBills()).length, 0);
    assert.equal((await ledger.snapshot()).sales.length, 0);
  } finally { await db?.close(); await rm(directory, { recursive: true, force: true }); }
});

test("BACKUP-01 failed image staging or database replacement leaves the active ledger and files intact", async () => {
  const source = await setup(), target = await setup();
  try {
    const images = new MemoryImages();
    const path = await images.put("data:image/jpeg;base64,SGVsbG8=");
    await source.ledger.saveProduct({ ...(await source.ledger.products())[0], image: path });
    await source.ledger.checkout(order());
    const backup = await createBackup(source.ledger, images);
    await target.ledger.checkout(order());
    await target.ledger.checkout(order());
    const before = await target.ledger.snapshot();
    const targetImages = new MemoryImages();
    const original = await targetImages.put("data:image/jpeg;base64,V29ybGQ=");
    await assert.rejects(restoreBackup(backup, target.ledger, { put: async () => { throw new Error("image disk full"); } }, () => database()), /disk full/);
    assert.deepEqual(await target.ledger.snapshot(), before);
    await target.db.exec("CREATE TRIGGER fail_restore BEFORE INSERT ON sales BEGIN SELECT RAISE(ABORT,'restore disk full'); END;");
    await assert.rejects(restoreBackup(backup, target.ledger, targetImages, () => database()), /disk full/);
    assert.deepEqual(await target.ledger.snapshot(), before);
    assert.equal(await targetImages.read(original), "data:image/jpeg;base64,V29ybGQ=");
    await target.db.exec("DROP TRIGGER fail_restore");
    await restoreBackup(backup, target.ledger, targetImages, () => database());
    assert.deepEqual(await target.ledger.snapshot(), await source.ledger.snapshot());
    assert.equal(await targetImages.read(path), await images.read(path));
  } finally { await source.db.close(); await target.db.close(); }
});

test("BACKUP-02 rechecksummed traversal, totals and sequence corruption are rejected before restore", async () => {
  const { ledger, db } = await setup();
  try {
    await ledger.checkout(order());
    const backup = JSON.parse(await createBackup(ledger, new MemoryImages()));
    const before = await ledger.snapshot();
    const mutations = [
      (d) => { d.tables.products[0].image = "../outside.jpg"; },
      (d) => { d.files["../../outside.jpg"] = "data:image/jpeg;base64,SGVsbG8="; },
      (d) => { d.tables.sequences[0].last_number = 0; },
      (d) => { d.tables.sale_lines[0].cgst_paise++; d.tables.sale_lines[0].sgst_paise--; },
      (d) => { delete d.tables.payments; },
    ];
    for (const mutate of mutations) {
      const data = JSON.parse(backup.payload); mutate(data);
      const payload = JSON.stringify(data);
      await assert.rejects(inspectBackup(JSON.stringify({ payload, sha256: await digest(payload) }), () => database()));
      assert.deepEqual(await ledger.snapshot(), before);
    }
    assert.deepEqual(Object.keys(before), Object.keys(TABLES));
  } finally { await db.close(); }
});

test("SQLITE-05 lost commit acknowledgement leaves one valid bill and retry recovers it", async () => {
  const { ledger, db } = await setup();
  try {
    const input = order();
    const commit = db.commit;
    db.commit = async () => { await commit(); throw new Error("Commit acknowledgement lost"); };
    await assert.rejects(ledger.checkout(input));
    db.commit = commit;
    const snapshot = await ledger.snapshot();
    assert.equal(snapshot.sales.length, 1);
    assert.equal(snapshot.payments.length, 1);
    assert.equal(snapshot.sale_lines.length, 1);
    const retry = await ledger.checkout(input);
    assert.equal(retry.id, snapshot.sales[0].id);
    assert.deepEqual(await ledger.snapshot(), snapshot);
  } finally { await db.close(); }
});

test("ACCESS-04 failed-login lockout survives a new access instance and expires without changing credentials", async () => {
  const { ledger, db } = await setup();
  const values = new Map();
  const session = { getItem: (k) => values.get(k), setItem: (k, v) => values.set(k, v), removeItem: (k) => values.delete(k) };
  let now = 1000;
  try {
    const access = new OwnerAccess(ledger, session, () => now);
    const account = await access.setup("audit-owner", "Fixture-owner-secret-123");
    access.lock();
    for (let i = 0; i < 5; i++) await assert.rejects(access.login("audit-owner", "wrong"), /incorrect/);
    const reopened = new OwnerAccess(ledger, session, () => now);
    await assert.rejects(reopened.login("audit-owner", "Fixture-owner-secret-123"), /Wait 30 seconds/);
    assert.equal(await reopened.unlocked(), false);
    now += 30000;
    await reopened.login("AUDIT-OWNER", "Fixture-owner-secret-123");
    assert.equal(await reopened.unlocked(), true);
    assert.deepEqual(await ledger.localSetting(ACCESS_KEY), account);
    assert.deepEqual(await ledger.localSetting("access-lockout"), { failures: 0, until: 0 });
    const emptySession = { getItem: () => null };
    assert.equal(await new OwnerAccess(ledger, emptySession).unlocked(), false);
  } finally { await db.close(); }
});

test("BACKUP-FOLDER-02 lost permissions and changed provider documents never replace the ledger", async () => {
  const { ledger, db } = await setup();
  const files = new Map();
  let permission = false;
  const transport = {
    status: async () => ({ connected: permission, name: "Synthetic folder" }),
    choose: async () => { permission = true; },
    list: async () => [...files.keys()].map((uri) => ({ uri, name: uri, modified: 1 })),
    write: async (name, source) => {
      if (!permission) throw new Error("Folder permission revoked");
      files.set(name, source); return { uri: name };
    },
    read: async (uri) => {
      if (!permission) throw new Error("Folder permission revoked");
      return files.get(uri);
    },
  };
  try {
    await ledger.checkout(order());
    const before = await ledger.snapshot();
    const service = new PersistentBackups({ ledger, images: new MemoryImages(), transport, makeDatabase: () => database() });
    await service.initialize();
    assert.deepEqual(await service.save(), { state: "not_configured" });
    await assert.rejects(service.discover(), /Reconnect/);
    await service.connect(); await service.save();
    const discovered = await service.discover();
    assert.equal(discovered.valid.length, 1);
    const candidate = discovered.valid[0];
    const changed = JSON.parse(files.get(candidate.uri)); changed.sha256 = "0".repeat(64);
    files.set(candidate.uri, JSON.stringify(changed));
    await assert.rejects(candidate.restore(), /changed/);
    permission = false;
    await assert.rejects(service.save(), /permission revoked/);
    assert.deepEqual(await ledger.snapshot(), before);
    assert.equal(files.size, 1);
  } finally { await db.close(); }
});

test("BACKUP-FOLDER-03 a provider read-back mismatch cannot be reported as successful backup", async () => {
  const { ledger, db } = await setup();
  try {
    await ledger.checkout(order());
    const valid = await createBackup(ledger, new MemoryImages());
    await ledger.checkout(order());
    const before = await ledger.snapshot();
    const statuses = [];
    const service = new PersistentBackups({
      ledger, images: new MemoryImages(), makeDatabase: () => database(), status: (s) => statuses.push(s),
      transport: { status: async () => ({ connected: true }), write: async () => ({ uri: "fixture" }), read: async () => valid },
    });
    await service.initialize();
    await assert.rejects(service.save(), /does not match/);
    assert.match(statuses.at(-1), /needs attention/);
    assert.deepEqual(await ledger.snapshot(), before);
  } finally { await db.close(); }
});
