import { test, expect } from "@playwright/test";
import { unlockInclusiveFixture as unlockFixture } from "./access-helper.js";

test("WASM-01 IndexedDB quota rejection rolls back checkout and retry creates one durable invoice", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.addInitScript(() => {
    const put = IDBObjectStore.prototype.put;
    IDBObjectStore.prototype.put = function (...args) {
      if (window.__rejectLedgerWrite && args[1] === "restaurant-sqlite-v1")
        throw new DOMException("Synthetic storage quota failure", "QuotaExceededError");
      return put.apply(this, args);
    };
  });
  await page.goto("/"); await unlockFixture(page);
  await page.locator('[data-product-id="menu-001"]').click();
  await expect(page.locator("#total-net")).toHaveText("₹170.00");
  await page.locator("#pay-button").click();
  await page.locator("#cash-tender").fill("200.00");
  await page.evaluate(() => { window.__rejectLedgerWrite = true; });
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-dialog")).not.toBeVisible();
  await expect(page.locator("body")).toContainText("Synthetic storage quota failure");
  await page.evaluate(() => { window.__rejectLedgerWrite = false; });
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-dialog")).toBeVisible();
  await expect(page.locator("#receipt-preview")).toContainText("000001");
  await page.reload();
  await expect(page.locator("#storage-status")).toContainText("SQLite");
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(1);
  await expect(page.locator("#sales-list")).toContainText("000001");
  expect(errors).toEqual([]);
});
