import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { unlockFixture } from "./access-helper.js";

const output = resolve("test-results/receipt-performance-2026-11-02");
mkdirSync(output, { recursive: true });

test("RECEIPT-ALIGN-01 GST values align beneath RATE in preview and 80 mm output without changing saved totals", async ({ page }) => {
  await page.goto("/"); await unlockFixture(page);
  await page.locator('.product-tile[data-product-id="menu-001"]').click();
  await page.locator("#pay-button").click();
  await page.locator("#complete-sale").click();
  const receipt = page.locator("#receipt-preview .receipt-paper");
  await expect(receipt.locator(".net")).toHaveText("TOTAL₹178.50");
  const alignment = async root => {
    const rate = await root.locator("thead th").nth(2).boundingBox();
    for (const key of ["discount", "taxable", "cgst", "sgst", "round"]) {
      const cell = root.locator(`[data-receipt-total="${key}"] .receipt-summary-value`);
      const bounds = await cell.boundingBox();
      expect(Math.abs(bounds.x - rate.x)).toBeLessThan(0.5);
      expect(Math.abs(bounds.x + bounds.width - rate.x - rate.width)).toBeLessThan(0.5);
      expect(await cell.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(false);
    }
    await expect(root.locator('[data-receipt-total="cgst"] .receipt-summary-value')).toHaveText("₹4.25");
    await expect(root.locator('[data-receipt-total="sgst"] .receipt-summary-value')).toHaveText("₹4.25");
  };
  await alignment(receipt);
  const saved = await receipt.innerHTML();
  await receipt.screenshot({ path: resolve(output, "receipt-gst-under-rate.png") });
  await page.evaluate(() => { window.print = () => {}; });
  await page.locator("#print-receipt").click();
  await page.emulateMedia({ media: "print" });
  const paper = page.locator("#print-document .receipt-paper");
  await alignment(paper);
  const bounds = await paper.boundingBox();
  await page.pdf({ path: resolve(output, "receipt-gst-under-rate-80mm.pdf"), width: "80mm", height: `${(bounds.height+2)/96*25.4}mm`, printBackground: true });
  await page.emulateMedia({ media: "screen" });
  await page.locator("#receipt-dialog [data-close]").click();
  await page.reload(); await page.locator("#last-receipt").click();
  await expect(receipt).toBeVisible();
  expect(await receipt.innerHTML()).toBe(saved);
});

test("COUNTER-PERF-01 taps render once, rapid quantities persist through checkout, and changed GST settings refresh quotes", async ({ page }) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/"); await unlockFixture(page);
  const result = await page.evaluate(async () => {
    let batches = 0;
    const observer = new MutationObserver(() => batches++);
    observer.observe(document.querySelector("#cart-lines"), { childList: true });
    document.querySelector('.product-tile[data-product-id="menu-001"]').click();
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    observer.disconnect();
    return { batches, total: document.querySelector("#total-net").textContent };
  });
  expect(result).toEqual({ batches: 1, total: "₹178.50" });
  await page.evaluate(() => {
    for (let index = 0; index < 19; index++) document.querySelector('.product-tile[data-product-id="menu-001"]').click();
  });
  await expect(page.locator('[data-quantity-input="menu-001"]')).toHaveValue("20.000");
  await expect(page.locator("#total-net")).toHaveText("₹3,570.00");
  await page.locator("#pay-button").click(); await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-preview .net")).toHaveText("TOTAL₹3570.00");
  await expect(page.locator("#receipt-preview tbody tr").first().locator("td").nth(1)).toHaveText("20");
  await page.locator("#receipt-dialog [data-close]").click();
  await page.locator('[data-nav="settings"]').click();
  await page.locator('#settings-form [name="tax_inclusive"]').selectOption("true");
  await page.locator('#settings-form .button-primary').click();
  await page.getByText("Setup saved locally", { exact: true }).waitFor();
  await page.locator('[data-nav="billing"]').click();
  await page.locator('.product-tile[data-product-id="menu-001"]').click();
  await expect(page.locator("#total-net")).toHaveText("₹170.00");
  await page.locator("#order-discount").fill("invalid");
  await expect(page.locator("#pay-button")).toBeDisabled();
  await expect(page.locator("#cart-error")).not.toBeEmpty();
  await page.locator("#order-discount").fill("10.00");
  await expect(page.locator("#total-net")).toHaveText("₹160.00");
  expect(errors).toEqual([]);
});

test("IMAGE-CACHE-UI-01 warm portion variants share local image reads and every original thumbnail decodes", async ({ page }) => {
  await page.addInitScript(() => {
    window.__photoReads = [];
    const get = IDBObjectStore.prototype.get;
    IDBObjectStore.prototype.get = function (key) {
      if (String(key).startsWith("restaurant:images/")) window.__photoReads.push(key);
      return get.call(this, key);
    };
  });
  await page.goto("/"); await unlockFixture(page);
  await expect(page.locator(".product-tile img")).toHaveCount(36);
  await page.reload();
  await expect(page.locator(".product-tile img")).toHaveCount(36);
  const reads = await page.evaluate(() => window.__photoReads);
  expect(reads.length).toBe(new Set(reads).size);
  expect(reads.length).toBe(23); // 22 original food images and the restaurant logo.
  expect(await page.locator(".product-tile img").evaluateAll(async images => {
    await Promise.all(images.map(image => image.decode()));
    return images.every(image => image.naturalWidth > 0);
  })).toBe(true);
});
