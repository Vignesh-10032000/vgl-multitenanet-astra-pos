import { Capacitor } from "@capacitor/core";
import { get, set } from "idb-keyval";
import { operationId } from "./domain.js";

/** Browser preview uses actual SQLite WASM; only Android uses the durable native database. */
export async function browserDatabase({ bytes, persist = false } = {}) {
  const [{ default: initialize }, { default: wasm }] = await Promise.all([
    import("sql.js"),
    import("sql.js/dist/sql-wasm.wasm?url"),
  ]);
  const SQL = await initialize({ locateFile: () => wasm });
  const saved = bytes || (persist ? await get("restaurant-sqlite-v1") : null);
  let db = saved ? new SQL.Database(saved) : new SQL.Database();
  let before;
  let inTransaction = false;
  return {
    async query(sql, values = []) {
      const statement = db.prepare(sql);
      try {
        statement.bind(values);
        const rows = [];
        while (statement.step()) rows.push(statement.getAsObject());
        return rows;
      } finally {
        statement.free();
      }
    },
    async run(sql, values = []) {
      db.run(sql, values);
    },
    async exec(sql) {
      db.run(sql);
    },
    async begin() {
      before = persist ? db.export() : null;
      db.run("PRAGMA foreign_keys=ON; BEGIN IMMEDIATE");
      inTransaction = true;
    },
    async commit() {
      db.run("COMMIT");
      inTransaction = false;
      if (persist) {
        try {
          await set("restaurant-sqlite-v1", db.export());
          db.run("PRAGMA foreign_keys=ON");
        } catch (error) {
          db.close();
          db = new SQL.Database(before);
          db.run("PRAGMA foreign_keys=ON");
          throw error;
        }
      }
      before = null;
    },
    async rollback() {
      // Persistence errors already replaced the in-memory connection with its committed predecessor.
      if (inTransaction) db.run("ROLLBACK");
      inTransaction = false;
      before = null;
    },
    async close() {
      db.close();
    },
  };
}

export async function openDatabase({ validation = false } = {}) {
  if (!Capacitor.isNativePlatform()) return browserDatabase({ persist: !validation });
  const { SQLiteConnection, CapacitorSQLite } = await import(
    "@capacitor-community/sqlite"
  );
  const sqlite = new SQLiteConnection(CapacitorSQLite);
  return nativeDatabase(sqlite, { validation });
}

/** Same SQLite contract for the live ledger and isolated backup validation. */
export async function nativeDatabase(sqlite, { validation = false } = {}) {
  // Backup validation uses an isolated native database, never the live ledger.
  const name = validation ? `validation_${operationId().replaceAll("-", "")}` : "restaurant";
  const db = await sqlite.createConnection(
    name,
    false,
    "no-encryption",
    1,
    false,
  );
  try {
    await db.open();
    await db.execute("PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL;", false);
  } catch (error) {
    try { await sqlite.closeConnection(name, false); }
    catch (closeError) { console.warn("Failed SQLite open cleanup", closeError); }
    throw error;
  }
  return {
    query: async (sql, values = []) =>
      (await db.query(sql, values)).values || [],
    run: (sql, values = []) => db.run(sql, values, false),
    exec: (sql) => db.execute(sql, false),
    begin: () => db.beginTransaction(),
    commit: () => db.commitTransaction(),
    rollback: () => db.rollbackTransaction(),
    close: async () => {
      try { if (validation) await db.delete(); }
      finally { await sqlite.closeConnection(name, false); }
    },
  };
}
