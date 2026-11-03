import { Capacitor } from "@capacitor/core";
import { get, set } from "idb-keyval";

/** Isolated in-memory SQLite for preview/backup inspection; never the Android ledger. */
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
  if (validation) throw new Error("Native backup validation is disabled; use isolated in-memory SQLite");
  if (!Capacitor.isNativePlatform()) return browserDatabase({ persist: true });
  const { SQLiteConnection, CapacitorSQLite } = await import(
    "@capacitor-community/sqlite"
  );
  const sqlite = new SQLiteConnection(CapacitorSQLite);
  return nativeDatabase(sqlite, { validation });
}

/** The native connection is reserved for the authoritative live ledger. */
export async function nativeDatabase(sqlite, { validation = false } = {}) {
  if (validation) throw new Error("Native backup validation is disabled; use isolated in-memory SQLite");
  const name = "restaurant";
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
    close: () => sqlite.closeConnection(name, false),
  };
}
