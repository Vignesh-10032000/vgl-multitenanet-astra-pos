import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import ExcelJS from "exceljs";
import { setup, database, defaults, menu, order, MemoryImages } from "../tests/restaurant/helpers.js";
import { Ledger } from "../restaurant/repository.js";
import { createBackup, restoreBackup } from "../restaurant/backup.js";
import { csv, xlsx } from "../restaurant/exports.js";

const args = Object.fromEntries(process.argv.slice(2).map((arg) => arg.replace(/^--/, "").split("=")));
const volumes = (args.bills || "100,500,1000").split(",").map(Number);
const cycles = Number(args.cycles || 100);
const catalogSize = Number(args.products || 1000);
if (volumes.some((n) => !Number.isInteger(n) || n < 1 || n > 10000) ||
    !Number.isInteger(cycles) || cycles < 1 || cycles > 10000 ||
    !Number.isInteger(catalogSize) || catalogSize < 36 || catalogSize > 10000)
  throw new Error("Use --bills=100,500,1000 --cycles=100 --products=1000 (bounded at 10000)");
const output = resolve("test-results/reliability-audit/stress");
await mkdir(output, { recursive: true });
const percentile = (values, fraction) => [...values].sort((a, b) => a - b)[Math.min(values.length - 1, Math.floor(values.length * fraction))];
const distribution = (values) => ({ count: values.length, median_ms: percentile(values, 0.5), p95_ms: percentile(values, 0.95), max_ms: Math.max(...values) });
const period = { from: "2026-10-01", to: "2026-10-31" };
const results = [];
for (const bills of volumes) {
  const directory = await mkdtemp(join(tmpdir(), "pos-stress-"));
  const path = join(directory, "synthetic.sqlite");
  let db, restored;
  const start = performance.now();
  try {
    let ledger;
    ({ db, ledger } = await setup({ path, now: () => "2026-10-31T04:00:00.000Z" }));
    await db.exec("PRAGMA synchronous=FULL");
    const images = new MemoryImages();
    // The existing manifest's public files are used verbatim, never regenerated.
    const { readdir } = await import("node:fs/promises");
    const photoPaths = [];
    for (const file of await readdir("restaurant/public/menu-photos/v1")) {
      if (!file.endsWith(".jpg")) continue;
      const bytes = await readFile(join("restaurant/public/menu-photos/v1", file));
      photoPaths.push(await images.put(`data:image/jpeg;base64,${bytes.toString("base64")}`));
    }
    assert.equal(photoPaths.length, 22);
    const products = await ledger.products();
    for (let i = 0; i < products.length; i++) await ledger.saveProduct({ ...products[i], image: photoPaths[i % photoPaths.length] });
    for (let i = 36; i < catalogSize; i++) await ledger.saveProduct({
      id: `synthetic-${i}`, name: `Synthetic dish ${i} தமிழ்`, portion: i % 2 ? "Half" : "Full",
      category: `Category ${i % 12}`, price_paise: 100 + i, image: photoPaths[i % photoPaths.length], active: true,
    });
    const catalog = await ledger.products();
    assert.equal(catalog.length, catalogSize);
    const latency = [], paymentTotals = { cash: 0, upi: 0 }, memory = [];
    let expected = 0, completed = 0;
    const requests = [];
    for (let i = 0; i < bills; i++) {
      const p = catalog[i % catalog.length], quantity = 1 + i % 4, discount_paise = i % 100;
      const total = p.price_paise * quantity - discount_paise;
      const cash = i % 3 === 0 ? total : i % 3 === 1 ? 0 : Math.floor(total / 2);
      const upi = total - cash;
      const payments = [];
      if (cash) payments.push({ method: "cash", amount_paise: cash, tendered_paise: cash + 3000 });
      if (upi) payments.push({ method: "upi", amount_paise: upi });
      requests.push(order({
        items: [{ product_id: p.id, name: p.name, portion: p.portion, unit_paise: p.price_paise, quantity }],
        discount_paise, payments,
      }));
      expected += total; paymentTotals.cash += cash; paymentTotals.upi += upi;
    }
    const billingStart = performance.now();
    // Promise batches reflect async callers; Ledger serializes the single writer.
    for (let offset = 0; offset < requests.length; offset += 8) {
      await Promise.all(requests.slice(offset, offset + 8).map(async (input) => {
        const started = performance.now();
        const sale = await ledger.checkout(input);
        latency.push(performance.now() - started);
        assert.equal(sale.total_paise, input.items[0].unit_paise * input.items[0].quantity - input.discount_paise);
        completed++;
      }));
      if (offset % 80 === 0) memory.push({ completed, ...process.memoryUsage() });
    }
    const billing_ms = performance.now() - billingStart;
    for (const input of requests.filter((_, i) => i % 10 === 0)) await ledger.checkout(input);
    const before = await ledger.snapshot();
    await ledger.saveDraft({ originalCart: [{ test: "preserve" }], operation: "failed-test" });
    await db.exec("CREATE TRIGGER audit_interrupt BEFORE INSERT ON payments BEGIN SELECT RAISE(ABORT,'controlled interruption'); END;");
    await assert.rejects(ledger.checkout(order()), /controlled interruption/);
    const after = await ledger.snapshot();
    for (const table of ["sales", "sale_lines", "payments", "sequences"]) assert.deepEqual(after[table], before[table]);
    await db.exec("DROP TRIGGER audit_interrupt");
    await ledger.saveDraft(null);
    const search = [];
    for (let i = 0; i < cycles; i++) {
      const started = performance.now();
      const rows = await ledger.products();
      const matches = rows.filter((p) => `${p.name} ${p.portion} ${p.category}`.toLowerCase().includes("synthetic"));
      assert.equal(matches.length, catalogSize - 36);
      search.push(performance.now() - started);
      const cart = { cart: [{ product_id: "menu-001", quantity: i + 1 }], saleUuid: `soak-${i}`, orderDiscount: 0 };
      await ledger.saveDraft({ originalCart: cart.cart });
      const held = await ledger.holdCart(cart, `Fixture ${i}`);
      assert.deepEqual((await ledger.recallHeldBill(held)).cart, cart.cart);
      assert.equal((await ledger.draft()).operation, cart.saleUuid);
      await ledger.saveDraft(null);
      if (i % 20 === 19) {
        await db.close(); db = database(path); ledger = new Ledger(db);
        await ledger.initialize(menu.items, defaults);
        memory.push({ cycle: i + 1, ...process.memoryUsage() });
      }
    }
    const reportStart = performance.now();
    const report = await ledger.report(period);
    const report_ms = performance.now() - reportStart;
    assert.equal(report.totals.bills, bills);
    assert.equal(report.totals.net_paise, expected);
    assert.equal(report.totals.cash_paise, paymentTotals.cash);
    assert.equal(report.totals.upi_paise, paymentTotals.upi);
    assert.equal(new Set(report.invoices.map((s) => s.bill_number)).size, bills);
    const csvStart = performance.now(), csvSource = csv(report);
    const csv_ms = performance.now() - csvStart;
    await writeFile(join(output, `${bills}-bills.csv`), csvSource);
    const xlsxStart = performance.now(), xlsxBytes = await xlsx(report);
    const xlsx_ms = performance.now() - xlsxStart;
    await writeFile(join(output, `${bills}-bills.xlsx`), xlsxBytes);
    const workbook = new ExcelJS.Workbook(); await workbook.xlsx.load(xlsxBytes);
    assert.equal(workbook.getWorksheet("Invoices").rowCount, bills + 1);
    let parsedTotal = 0n;
    workbook.getWorksheet("Invoices").eachRow((row, index) => {
      if (index > 1) {
        const [whole, fraction = ""] = String(row.getCell(11).value).split(".");
        parsedTotal += BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
      }
    });
    assert.equal(parsedTotal, BigInt(expected));
    const snapshot = await ledger.snapshot(), backupStart = performance.now();
    const backup = await createBackup(ledger, images), backup_ms = performance.now() - backupStart;
    restored = await setup(); const restoredImages = new MemoryImages();
    const restoreStart = performance.now();
    await restoreBackup(backup, restored.ledger, restoredImages, () => database());
    const restore_ms = performance.now() - restoreStart;
    assert.deepEqual(await restored.ledger.snapshot(), snapshot);
    assert.deepEqual(restoredImages.files, images.files);
    assert.deepEqual(await db.query("PRAGMA foreign_key_check"), []);
    assert.equal((await db.query("PRAGMA integrity_check"))[0].integrity_check, "ok");
    const bytes = (await stat(path)).size;
    await db.close(); db = database(path); ledger = new Ledger(db);
    assert.deepEqual(await ledger.snapshot(), snapshot);
    const result = {
      bills, completed, duplicate_invoices: 0, unexpected_failures: 0, injected_failures: 1,
      catalog_size: catalogSize, draft_hold_cycles: cycles, photo_files: images.files.size,
      billing_ms, checkout_with_queue: distribution(latency), catalog_query_and_filter: distribution(search),
      report_ms, csv_ms, xlsx_ms, backup_ms, restore_ms, database_bytes: bytes,
      backup_bytes: Buffer.byteLength(backup), xlsx_bytes: xlsxBytes.byteLength,
      totals_paise: { net: expected, ...paymentTotals }, memory_samples: memory,
      elapsed_ms: performance.now() - start,
    };
    results.push(result); console.log(JSON.stringify(result));
  } finally {
    await db?.close(); await restored?.db.close();
    await rm(directory, { recursive: true, force: true });
  }
}
await writeFile(join(output, "results.json"), JSON.stringify({
  scope: "Desktop Node SQLite, synthetic disposable files, not Android/TVS performance acceptance. Queue latency includes serialized callers. Memory samples include garbage-collection effects; bounded cycles do not prove leak absence.",
  timestamp: new Date().toISOString(), node: process.version, platform: process.platform,
  architecture: process.arch, results,
}, null, 2));
