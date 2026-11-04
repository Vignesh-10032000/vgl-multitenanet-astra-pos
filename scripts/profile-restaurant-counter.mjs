import { chromium } from "@playwright/test";
import { preview } from "vite";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setup, order, currentDefaults, MemoryImages } from "../tests/restaurant/helpers.js";
import { createBackup } from "../restaurant/backup.js";
import { installMenuPhotos, restoreMenuIllustrations } from "../restaurant/menu-photo-install.js";
import { unlockFixture } from "../tests/restaurant-browser/access-helper.js";
import { decimal } from "../restaurant/domain.js";

// Disposable SQLite/browser fixtures only. This is a repeatable desktop diagnostic,
// not a claim that CPU throttling reproduces the TVS's processor or storage.
const label = process.argv[2] || "current";
if (!/^[a-z0-9-]+$/.test(label)) throw new Error("Use a simple profile label");
const output = resolve("test-results/receipt-performance-2026-11-02");
await mkdir(output, { recursive: true });
const fixture = await setup({ settings: currentDefaults, now: () => "2026-11-02T05:00:00.000Z" });
let backup;
try {
  const images = new MemoryImages();
  const readPhoto = async asset => `data:image/jpeg;base64,${(await readFile(resolve("restaurant/public", asset.src))).toString("base64")}`;
  const manifest = JSON.parse(await readFile("restaurant/menu-photos.json", "utf8"));
  await installMenuPhotos({ ledger: fixture.ledger, images, manifest, readPhoto });
  await restoreMenuIllustrations({ ledger: fixture.ledger, images, manifest: JSON.parse(await readFile("restaurant/menu-photo-restore.json", "utf8")), readPhoto });
  for (let index = 0; index < 1000; index++) await fixture.ledger.checkout(order());
  backup = await createBackup(fixture.ledger, images);
} finally { await fixture.db.close(); }

const server = await preview({ configFile: resolve("restaurant/vite.config.js"), preview: { host: "127.0.0.1", port: 5176, strictPort: true } });
let browser, profilePage;
try {
  browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage(), errors = [];
  profilePage = page;
  page.on("pageerror", error => errors.push(error.message));
  await page.addInitScript(() => {
    window.__imageReads = 0;
    const get = IDBObjectStore.prototype.get;
    IDBObjectStore.prototype.get = function (key) {
      if (String(key).startsWith("restaurant:images/")) window.__imageReads++;
      return get.call(this, key);
    };
  });
  await page.goto("http://127.0.0.1:5176"); await unlockFixture(page);
  await page.locator('[data-nav="settings"]').click();
  await page.locator("#restore-file").setInputFiles({ name: "synthetic-1000-images.json", mimeType: "application/json", buffer: Buffer.from(backup) });
  await page.locator("#restore-confirm").fill("RESTORE");
  const restored = page.waitForEvent("load");
  await page.locator("#restore-button").click(); await restored;
  await expectReady();
  await page.locator('[data-nav="billing"]').click();
  const warm = [];
  for (let index = 0; index < 3; index++) {
    await page.reload(); await expectReady();
    warm.push(await page.evaluate(() => ({ ready_ms: performance.getEntriesByName("restaurant:ready")[0].startTime, image_storage_reads: window.__imageReads })));
  }
  const session = await context.newCDPSession(page);
  await page.locator('[data-nav="sales"]').click();
  await page.locator('#sales-filter [name="from"]').fill("2026-11-02");
  await page.locator('#sales-filter [name="to"]').fill("2026-11-02");
  await page.locator('#sales-filter button[type="submit"]').click();
  await page.waitForFunction(() => document.querySelector("#sales-pagination").textContent.includes("of 1000 bills"));
  await page.locator('[data-nav="billing"]').click();
  await session.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  const samples = [];
  for (let count = 1; count <= 20; count++) {
    const expected = decimal(count * 17850);
    samples.push(await page.evaluate(async expected => {
      const start = performance.now();
      let batches = 0;
      const paint = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => { observer.disconnect(); reject(new Error("Total never became ready")); }, 10000);
        const observer = new MutationObserver(() => {
          batches++;
          if (document.querySelector("#total-net").textContent.replace(/[₹,]/g, "") !== expected || document.querySelector("#pay-button").disabled) return;
          observer.disconnect(); clearTimeout(timeout);
          requestAnimationFrame(() => requestAnimationFrame(() => resolve(performance.now() - start)));
        });
        observer.observe(document.querySelector("#cart-lines"), { childList: true });
        document.querySelector('.product-tile[data-product-id="menu-001"]').click();
      });
      return { tap_to_total_paint_ms: await paint, cart_render_batches: batches };
    }, expected));
    await page.waitForFunction(() => document.querySelector("#draft-status").textContent === "Cart saved locally");
  }
  await session.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  await session.send("HeapProfiler.collectGarbage");
  const heap = await session.send("Runtime.getHeapUsage");
  const summary = values => { const sorted = [...values].sort((a,b) => a-b); return { median: sorted[Math.floor(sorted.length/2)], p95: sorted[Math.floor(sorted.length*0.95)], min: sorted[0], max: sorted.at(-1) }; };
  const result = {
    scope: "Desktop Chromium only; 4x CPU slowdown for taps, unthrottled warm startup; no TVS or native-storage acceptance claim.",
    label, browser: browser.version(), synthetic_bills: 1000, menu_images: 22,
    warm_startup: warm,
    tap_to_total_paint_ms: summary(samples.map(sample => sample.tap_to_total_paint_ms)),
    render_batches: summary(samples.map(sample => sample.cart_render_batches)),
    samples, js_heap_used_bytes: heap.usedSize, page_errors: errors,
  };
  await writeFile(resolve(output, `${label}-counter.json`), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  if (errors.length) throw new Error("Profile recorded browser errors");
  async function expectReady() {
    await page.waitForFunction(() => !!performance.getEntriesByName("restaurant:ready").length);
    await page.locator("#access-screen").waitFor({ state: "hidden" });
    await page.locator(".product-tile").first().waitFor({ state: "attached" });
  }
} catch (error) {
  if (profilePage) console.error(await profilePage.evaluate(() => ({ ready: document.querySelector("#storage-status")?.textContent, locked: document.body.dataset.locked, backup: document.querySelector("#backup-status")?.textContent, marks: performance.getEntriesByType("mark").map(mark => mark.name) })));
  throw error;
} finally {
  await browser?.close();
  await new Promise(resolve => server.httpServer.close(resolve));
}
