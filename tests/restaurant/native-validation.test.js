import test from "node:test";
import assert from "node:assert/strict";
import { nativeDatabase } from "../../restaurant/drivers.js";
import { database, setup, MemoryImages, order } from "./helpers.js";
import { createBackup, inspectBackup } from "../../restaurant/backup.js";

function bridge({ failOpen = false } = {}) {
  const calls = [], db = database();
  return { calls, sqlite: {
    async createConnection(name) {
      calls.push(["create", name]);
      return {
        open: async () => { if (failOpen) throw new Error("open failed"); },
        execute: sql => { calls.push(["exec", sql]); return db.exec(sql); },
        query: async (sql, values) => ({ values: await db.query(sql, values) }),
        run: (sql, values) => db.run(sql, values),
        beginTransaction: () => db.begin(), commitTransaction: () => db.commit(), rollbackTransaction: () => db.rollback(),
        delete: async () => { calls.push(["delete", name]); },
      };
    },
    async closeConnection(name) { calls.push(["close", name]); await db.close(); },
  } };
}

test("NATIVE-VALIDATION-01 complete backup validates through native bridge contract, isolated from the live name", async () => {
  const { db, ledger } = await setup();
  try {
    await ledger.checkout(order());
    const source = await createBackup(ledger, new MemoryImages());
    const fake = bridge();
    const validated = await inspectBackup(source, () => nativeDatabase(fake.sqlite, { validation: true }));
    assert.deepEqual(validated.tables, await ledger.snapshot());
    const name = fake.calls[0][1];
    assert.match(name, /^validation_[a-f0-9]{32}$/);
    assert.deepEqual(fake.calls.filter(call => ["delete", "close"].includes(call[0])), [["delete", name], ["close", name]]);
    assert.ok(fake.calls.some(call => call[1].includes("synchronous=FULL")));
  } finally { await db.close(); }
});

test("NATIVE-VALIDATION-02 normal connection never deletes the live database; failed opens close safely", async () => {
  const normal = bridge();
  await (await nativeDatabase(normal.sqlite)).close();
  assert.deepEqual(normal.calls.filter(call => call[0] !== "exec"), [["create", "restaurant"], ["close", "restaurant"]]);
  const failed = bridge({ failOpen: true });
  await assert.rejects(nativeDatabase(failed.sqlite), /open failed/);
  assert.deepEqual(failed.calls, [["create", "restaurant"], ["close", "restaurant"]]);
});
