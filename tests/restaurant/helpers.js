import { DatabaseSync } from "node:sqlite";
import { Ledger } from "../../restaurant/repository.js";
import { readFileSync } from "node:fs";
export const menu = JSON.parse(
  readFileSync(
    new URL("../../resources/menu-transcription.json", import.meta.url),
  ),
);
export const currentDefaults = JSON.parse(
  readFileSync(
    new URL("../../restaurant/store-defaults.json", import.meta.url),
  ),
);
// Preserve the historical inclusive-GST regression fixtures explicitly. New owner
// pricing is covered separately with currentDefaults and fresh browser setup.
export const defaults = { ...currentDefaults, tax_inclusive: true };
export function database(path = ":memory:") {
  const db = new DatabaseSync(path);
  return {
    query: async (sql, args = []) =>
      db
        .prepare(sql)
        .all(...args)
        .map((row) => ({ ...row })),
    run: async (sql, args = []) => db.prepare(sql).run(...args),
    exec: async (sql) => db.exec(sql),
    begin: async () => db.exec("BEGIN IMMEDIATE"),
    commit: async () => db.exec("COMMIT"),
    rollback: async () => db.exec("ROLLBACK"),
    close: async () => db.close(),
  };
}
export async function setup(options = {}) {
  const db = database(options.path);
  const ledger = new Ledger(db, options);
  await ledger.initialize(menu.items, options.settings || defaults);
  return { db, ledger };
}
export function order(override = {}) {
  return {
    operation_id: crypto.randomUUID(),
    items: [
      {
        product_id: "menu-001",
        name: "CHICKEN BIRIYANI",
        portion: "Standard",
        unit_paise: 17000,
        quantity: 1,
      },
    ],
    discount_paise: 0,
    method: "cash",
    tendered_paise: 20000,
    ...override,
  };
}
export class MemoryImages {
  files = new Map();
  async read(path) {
    if (!this.files.has(path)) throw new Error("Missing image");
    return this.files.get(path);
  }
  async put(data) {
    const { digest } = await import("../../restaurant/assets.js");
    const path = `images/${await digest(data)}.jpg`;
    this.files.set(path, data);
    return path;
  }
}
