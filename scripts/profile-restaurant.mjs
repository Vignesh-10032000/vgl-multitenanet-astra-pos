import { chromium } from "@playwright/test";
import { preview } from "vite";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { setup, order } from "../tests/restaurant/helpers.js";
import { createBackup } from "../restaurant/backup.js";
import { unlockInclusiveFixture as unlockFixture } from "../tests/restaurant-browser/access-helper.js";

// All data lives in a disposable browser context and a disposable in-memory ledger.
const output = resolve("test-results/restaurant-performance");
await mkdir(output, { recursive: true });
const server = await preview({
  configFile: resolve("restaurant/vite.config.js"),
  preview: { host: "127.0.0.1", port: 5176, strictPort: true },
});
let browser;
try {
  browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const cdp = await context.newCDPSession(page);
  await cdp.send("Performance.enable");
  await cdp.send("HeapProfiler.enable");
  await cdp.send("Tracing.start", {
    categories:
      "devtools.timeline,blink.user_timing,v8.execute,disabled-by-default-devtools.timeline",
    transferMode: "ReturnAsStream",
  });
  await page.goto("http://127.0.0.1:5176");
  await unlockFixture(page);
  await page.locator("#storage-status").filter({ hasText: "SQLite" }).waitFor();
  const startup = await page.evaluate(() => ({
    ready_ms:
      performance.getEntriesByName("restaurant:ready")[0]?.startTime ?? null,
    navigation: performance.getEntriesByType("navigation")[0].toJSON(),
    user_agent: navigator.userAgent,
  }));
  await page.evaluate(() => {
    window.__touchSamples = [];
    document.querySelector("#pos-product-grid").addEventListener(
      "pointerdown",
      () => {
        const start = performance.now();
        const observer = new MutationObserver(() => {
          observer.disconnect();
          requestAnimationFrame(() =>
            requestAnimationFrame(() => {
              window.__touchSamples.push(performance.now() - start);
            }),
          );
        });
        observer.observe(document.querySelector("#cart-lines"), {
          childList: true,
        });
      },
      true,
    );
  });
  const memory = async () => {
    await page.waitForFunction(() => !document.querySelector(".toast"));
    await cdp.send("HeapProfiler.collectGarbage");
    const { metrics } = await cdp.send("Performance.getMetrics");
    const counters = await cdp.send("Memory.getDOMCounters");
    return {
      ...Object.fromEntries(
        metrics
          .filter((m) =>
            [
              "JSHeapUsedSize",
              "JSHeapTotalSize",
              "Documents",
              "Nodes",
              "JSEventListeners",
            ].includes(m.name),
          )
          .map((m) => [m.name, m.value]),
      ),
      dom: counters,
    };
  };
  const cycle = async () => {
    await page.locator('[data-product-id="menu-001"]').click();
    await page.locator('[data-quantity-action="increment"]').click();
    await page.waitForFunction(
      () => document.querySelector("#total-net").textContent === "₹340.00",
    );
    await page.locator("#clear-cart").click();
    await page.locator('[data-nav="products"]').click();
    await page.locator('[data-nav="sales"]').click();
    await page.locator('[data-nav="billing"]').click();
  };
  for (let i = 0; i < 3; i++) await cycle();
  const baseline = await memory();
  for (let i = 0; i < 10; i++) await cycle();
  const after10 = await memory();
  for (let i = 0; i < 10; i++) await cycle();
  const after20 = await memory();
  const touch = await page.evaluate(() => window.__touchSamples);
  touch.sort((a, b) => a - b);

  const { ledger, db } = await setup();
  let backup;
  try {
    for (let i = 0; i < 1000; i++) await ledger.checkout(order());
    backup = await createBackup(ledger, {
      read() {
        throw new Error("Fixture unexpectedly contains images");
      },
    });
  } finally {
    await db.close();
  }
  await page.locator('[data-nav="settings"]').click();
  await page
    .locator("#restore-file")
    .setInputFiles({
      name: "synthetic-1000-bills.json",
      mimeType: "application/json",
      buffer: Buffer.from(backup),
    });
  await page.locator("#restore-confirm").fill("RESTORE");
  await page.locator("#restore-button").click();
  await page.locator("#storage-status").filter({ hasText: "SQLite" }).waitFor();
  const reportStart = performance.now();
  await page.locator('[data-nav="sales"]').click();
  await page.waitForFunction(
    () => document.querySelectorAll("#sales-list tbody tr").length === 10 && document.querySelector("#sales-pagination").textContent.includes("of 1000 bills"),
  );
  await page.evaluate(
    () =>
      new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))),
  );
  const report_ms = performance.now() - reportStart;
  const csvStart = performance.now();
  await page.locator('[data-nav="reports"]').click();
  const downloadPromise = page.waitForEvent("download");
  await page.locator('[data-export="csv"]').click();
  const download = await downloadPromise;
  await download.saveAs(resolve(output, "synthetic-1000-bills.csv"));
  const csv_ms = performance.now() - csvStart;
  await page.screenshot({ path: resolve(output, "synthetic-1000-bills.png") });
  const complete = new Promise((r) => cdp.once("Tracing.tracingComplete", r));
  await cdp.send("Tracing.end");
  const { stream } = await complete;
  let trace = "";
  for (;;) {
    const chunk = await cdp.send("IO.read", { handle: stream });
    trace += chunk.data;
    if (chunk.eof) break;
  }
  await cdp.send("IO.close", { handle: stream });
  await writeFile(resolve(output, "desktop-chrome-trace.json"), trace);
  const result = {
    scope:
      "Desktop Chromium, isolated synthetic data. These are not TVS or Android measurements, and memory counters are not a proof of absence of leaks.",
    timestamp: new Date().toISOString(),
    browser: browser.version(),
    startup,
    touch_to_cart_paint_ms: {
      samples: touch.length,
      median: touch[Math.floor(touch.length / 2)],
      p95: touch[Math.floor(touch.length * 0.95)],
      max: touch.at(-1),
    },
    memory: { baseline, after10, after20 },
    synthetic_report: {
      bills: 1000,
      render_with_automation_overhead_ms: report_ms,
      csv_download_with_automation_overhead_ms: csv_ms,
    },
    page_errors: errors,
  };
  await writeFile(
    resolve(output, "desktop-metrics.json"),
    JSON.stringify(result, null, 2),
  );
  console.log(JSON.stringify(result, null, 2));
  if (errors.length)
    throw new Error("Browser errors recorded during profiling");
} finally {
  await browser?.close();
  await new Promise((r) => server.httpServer.close(r));
}
