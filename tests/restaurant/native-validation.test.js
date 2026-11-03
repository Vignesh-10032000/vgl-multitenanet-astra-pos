import test from "node:test";
import assert from "node:assert/strict";
import { nativeDatabase, openDatabase } from "../../restaurant/drivers.js";
import { database } from "./helpers.js";

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

test("NATIVE-VALIDATION-01 inspection cannot open or mutate the native live connection", async () => {
  const calls=[];
  await assert.rejects(nativeDatabase({ createConnection: () => { calls.push('create'); } }, { validation: true }), /disabled/);
  await assert.rejects(openDatabase({ validation: true }), /disabled/);
  assert.deepEqual(calls, []);
});

test("NATIVE-VALIDATION-02 normal connection never deletes the live database; failed opens close safely", async () => {
  const normal = bridge();
  await (await nativeDatabase(normal.sqlite)).close();
  assert.deepEqual(normal.calls.filter(call => call[0] !== "exec"), [["create", "restaurant"], ["close", "restaurant"]]);
  const failed = bridge({ failOpen: true });
  await assert.rejects(nativeDatabase(failed.sqlite), /open failed/);
  assert.deepEqual(failed.calls, [["create", "restaurant"], ["close", "restaurant"]]);
});
