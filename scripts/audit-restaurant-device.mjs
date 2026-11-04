import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { build } from "esbuild";

// Development-only bridge checks. Never installs, restarts, unlocks, prints, restores
// or writes to the owner's restaurant database. Each write targets a new audit UUID.
const serial = process.argv.find((a) => a.startsWith("--device="))?.slice(9);
if (!serial) throw new Error("Specify the connected --device=SERIAL explicitly");
const adb = resolve(".tools/android-sdk/platform-tools/adb.exe");
const adbCall = (...args) => execFileSync(adb, ["-s", serial, ...args], { encoding: "utf8" }).trim();
const pid = adbCall("shell", "pidof", "in.vgl.restaurant").split(" ")[0];
if (!/^\d+$/.test(pid)) throw new Error("The owner's app must already be running; this script does not launch it");
const port = "9231";
adbCall("forward", `tcp:${port}`, `localabstract:webview_devtools_remote_${pid}`);
const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
const target = pages.find((p) => p.url.startsWith("https://localhost/"));
if (!target) throw new Error("No restaurant WebView target");
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((done, reject) => { socket.onopen = done; socket.onerror = reject; });
let id = 0;
const pending = new Map();
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const handler = pending.get(data.id);
  if (!handler) return;
  pending.delete(data.id); clearTimeout(handler.timer);
  if (data.error) handler.reject(new Error(JSON.stringify(data.error)));
  else handler.resolve(data.result);
};
const evaluate = async (expression) => {
  const result = await new Promise((resolve, reject) => {
    const request = ++id;
    const timer = setTimeout(() => { pending.delete(request); reject(new Error("Device evaluation timeout")); }, 120000);
    pending.set(request, { resolve, reject, timer });
    socket.send(JSON.stringify({ id: request, method: "Runtime.evaluate", params: { expression, awaitPromise: true, returnByValue: true } }));
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
  return result.result.value;
};
const output = resolve("test-results/reliability-audit/device");
await mkdir(output, { recursive: true });
try {
  // Bundle only local pure definitions. No app startup code or storage singleton is run.
  const bundled = await build({
    stdin: { contents: 'export { createBackup, restoreBackup } from "./restaurant/backup.js"; export { Ledger } from "./restaurant/repository.js"; export { TABLES } from "./restaurant/schema.js";', resolveDir: process.cwd() },
    bundle: true, format: "iife", globalName: "__VGLAuditBackup", write: false,
    platform: "browser", target: "es2020",
  });
  const menu = JSON.parse(await readFile("resources/menu-transcription.json", "utf8"));
  const defaults = JSON.parse(await readFile("restaurant/store-defaults.json", "utf8"));
  const expression = `(${async function (input) {
    const { Ledger, TABLES } = window.__VGLAuditBackup;
    const plugin = window.Capacitor.Plugins.CapacitorSQLite;
    const check = (condition, message) => { if (!condition) throw new Error(message); };
    const hash = async (value) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(JSON.stringify(value))))].map((v) => v.toString(16).padStart(2, "0")).join("");
    const ownerState = async () => {
      const tables = {}, counts = {};
      for (const name of Object.keys(TABLES)) {
        const rows = (await plugin.query({ database: "restaurant", statement: `SELECT * FROM ${name}`, values: [], readonly: false })).values || [];
        tables[name] = rows.map((r) => Object.fromEntries(Object.keys(r).sort().map((k) => [k, r[k]]))).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b)));
        counts[name] = rows.length;
      }
      const folder = await window.Capacitor.Plugins.RestaurantBackup.folderStatus();
      let backups = [];
      if (folder.connected) backups = (await window.Capacitor.Plugins.RestaurantBackup.listBackups()).files;
      return { digest: await hash(tables), counts, shared_backup_count: backups.length, shared_backup_digest: await hash(backups), cart: document.querySelector("#total-net")?.textContent, qr_visible: document.querySelector("#payment-qr-dialog")?.open || false };
    };
    const before = await ownerState();
    const databases = [], timings = [];
    const open = async (name) => {
      check(/^audit_[a-f0-9_]+$/.test(name), "Unsafe synthetic database name");
      await plugin.createConnection({ database: name, version: 1, encrypted: false, mode: "no-encryption", readonly: false });
      await plugin.open({ database: name, readonly: false });
      const options = { database: name, readonly: false };
      const db = {
        query: async (statement, values = []) => (await plugin.query({ ...options, statement, values })).values || [],
        run: (statement, values = []) => plugin.run({ ...options, statement, values, transaction: false, returnMode: "no" }),
        exec: (statements) => plugin.execute({ ...options, statements, transaction: false }),
        begin: () => plugin.beginTransaction(options), commit: () => plugin.commitTransaction(options), rollback: () => plugin.rollbackTransaction(options),
        close: () => plugin.closeConnection(options),
      };
      await db.exec("PRAGMA foreign_keys=ON; PRAGMA synchronous=FULL;");
      return db;
    };
    const name = `audit_${input.id.replaceAll("-", "_")}`;
    databases.push(name);
    let db, target;
    let outcome;
    try {
      db = await open(name);
      let ledger = new Ledger(db, { now: () => "2026-10-31T04:00:00.000Z" });
      await ledger.initialize(input.menu, input.defaults);
      const images = { files: new Map(), async put(data) { const bytes = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(data)))].map((v) => v.toString(16).padStart(2, "0")).join(""); const path = `images/${bytes}.jpg`; this.files.set(path, data); return path; }, async read(path) { if (!this.files.has(path)) throw new Error("Missing test image"); return this.files.get(path); } };
      const image = await images.put("data:image/jpeg;base64,SGVsbG8=");
      await ledger.saveProduct({ ...(await ledger.products())[0], image });
      const request = (i) => ({ operation_id: `native-audit-${i}`, items: [{ product_id: "menu-001", name: "CHICKEN BIRIYANI", portion: "Standard", unit_paise: 17000, quantity: 1 }], discount_paise: i % 100, payments: [{ method: "cash", amount_paise: 7000, tendered_paise: 10000 }, { method: "upi", amount_paise: 10000 - i % 100 }] });
      const first = request(0);
      const retries = await Promise.all(Array.from({ length: 8 }, () => ledger.checkout(first)));
      check(new Set(retries.map((s) => s.id)).size === 1, "Native duplicate checkout");
      await ledger.saveDraft({ originalCart: [{ synthetic: true }], operation: "native-failure" });
      const prior = JSON.stringify(await ledger.snapshot());
      await db.exec("CREATE TRIGGER audit_fail BEFORE INSERT ON payments WHEN NEW.method='upi' BEGIN SELECT RAISE(ABORT,'native injected failure'); END;");
      let rejected = false;
      try { await ledger.checkout(request(1)); } catch (e) { rejected = /native injected failure/.test(e.message); }
      check(rejected, "Native second-tender failure was not rejected");
      check(JSON.stringify(await ledger.snapshot()) === prior, "Native rollback changed prior state");
      await db.exec("DROP TRIGGER audit_fail");
      for (let i = 1; i < 50; i++) {
        const start = performance.now();
        const sale = await ledger.checkout(request(i));
        timings.push(performance.now() - start);
        check(sale.total_paise === 17000 - i, "Native financial mismatch");
        check(sale.payments[0].change_paise === 3000, "Native change mismatch");
      }
      const snapshot = await ledger.snapshot();
      check(snapshot.sales.length === 50, "Native bill count mismatch");
      check(new Set(snapshot.sales.map((s) => s.bill_number)).size === 50, "Native invoice uniqueness failed");
      await db.close(); db = await open(name); ledger = new Ledger(db);
      check(JSON.stringify(await ledger.snapshot()) === JSON.stringify(snapshot), "Native close/reopen lost bills");
      const backup = await window.__VGLAuditBackup.createBackup(ledger, images);
      const restoreName = `${name}_b`; databases.push(restoreName);
      target = await open(restoreName); const restored = new Ledger(target);
      await restored.initialize([], input.defaults);
      await window.__VGLAuditBackup.restoreBackup(backup, restored, images, async () => {
        const scratchName = `${name}_c`; databases.push(scratchName);
        return open(scratchName);
      });
      check(JSON.stringify(await restored.snapshot()) === JSON.stringify(snapshot), "Native restore changed snapshot");
      check((await db.query("PRAGMA integrity_check"))[0].integrity_check === "ok", "Native integrity check failed");
      check((await db.query("PRAGMA foreign_key_check")).length === 0, "Native foreign-key check failed");
      const report = await ledger.report({ from: "2026-10-01", to: "2026-10-31" });
      check(report.totals.net_paise === 848775, "Native report does not reconcile");
      outcome = { synthetic_bills: 50, retry_requests: 8, injected_second_tender_failures: 1, integrity: "ok", foreign_key_errors: 0, restored_snapshot_equal: true, net_paise: report.totals.net_paise, checkout_ms: timings, user_agent: navigator.userAgent };
    } finally {
      await db?.close(); await target?.close();
      // Only close the isolated connections. Keep these named test DB files for inspection.
    }
    const after = await ownerState();
    check(JSON.stringify(after) === JSON.stringify(before), "Owner state changed during synthetic audit; inspect before continuing");
    return { ...outcome, owner_state_unchanged: true, before, after, synthetic_database_names: databases };
  }})(${JSON.stringify({ menu: menu.items, defaults, id: crypto.randomUUID() })})`;
  await evaluate(bundled.outputFiles[0].text);
  const start = performance.now();
  const result = await evaluate(expression);
  result.elapsed_ms = performance.now() - start;
  result.scope = "Local working Ledger source injected into already-running 1.0.9 WebView; actual Capacitor SQLite bridge and independent audit databases. Not installation testing of the rebuilt APK, TVS acceptance, app process death, SAF reinstall or physical printing.";
  result.device = { serial, model: adbCall("shell", "getprop", "ro.product.model"), android: adbCall("shell", "getprop", "ro.build.version.release") };
  assert.equal(result.owner_state_unchanged, true);
  await writeFile(resolve(output, "results.json"), JSON.stringify(result, null, 2));
  await writeFile(resolve(output, "memory.txt"), adbCall("shell", "dumpsys", "meminfo", "in.vgl.restaurant"));
  console.log(JSON.stringify(result, null, 2));
} finally {
  await evaluate("__VGLAuditBackup = undefined").catch(() => {});
  socket.close(); adbCall("forward", "--remove", `tcp:${port}`);
}
