import { test, expect } from "@playwright/test";
import { setup, order, MemoryImages, currentDefaults } from "../restaurant/helpers.js";
import { createBackup } from "../../restaurant/backup.js";
import { unlockFixture } from "./access-helper.js";

test("BACKUP-INSPECTION-01 inspecting a different ledger with native platform enabled cannot replace live data", async ({ page }) => {
  const fixture = await setup({ settings: currentDefaults });
  let candidate;
  try {
    await fixture.ledger.checkout(order());
    candidate = await createBackup(fixture.ledger, new MemoryImages());
  } finally { await fixture.db.close(); }
  await page.goto("/"); await unlockFixture(page);
  await expect(page.locator("#access-recover")).toBeEnabled();
  for (const id of ["menu-001", "menu-002"]) {
    await page.locator(`.product-tile[data-product-id="${id}"]`).click();
    await page.locator("#pay-button").click(); await page.locator("#complete-sale").click();
    await expect(page.locator("#receipt-dialog")).toBeVisible();
    await page.locator("#receipt-dialog [data-close]").click();
  }
  const digest = () => page.evaluate(async () => {
    const bytes = await new Promise((resolve,reject) => {
      const request=indexedDB.open("keyval-store");
      request.onsuccess=() => { const db=request.result, read=db.transaction("keyval").objectStore("keyval").get("restaurant-sqlite-v1"); read.onsuccess=() => {db.close();resolve(read.result);};read.onerror=() => reject(read.error); };
      request.onerror=() => reject(request.error);
    });
    return [...new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))].map(byte=>byte.toString(16).padStart(2,"0")).join("");
  });
  const before=await digest();
  await page.locator('[data-nav="settings"]').click();
  await page.evaluate(() => {
    window.inspectionOriginalPlatform=window.Capacitor.isNativePlatform;
    window.Capacitor.isNativePlatform=() => true;
  });
  try {
    await page.locator("#restore-file").setInputFiles({name:"different-one-bill.json",mimeType:"application/json",buffer:Buffer.from(candidate)});
    await expect(page.locator("#restore-dialog")).toBeVisible();
    await expect(page.locator("#restore-button")).toBeDisabled();
    await expect(page.locator("#restore-summary")).toContainText("1 bills");
    await page.locator("#restore-dialog [data-close]").last().click();
  } finally {
    await page.evaluate(() => { window.Capacitor.isNativePlatform=window.inspectionOriginalPlatform;delete window.inspectionOriginalPlatform; });
  }
  expect(await digest()).toBe(before);
  await page.locator('[data-nav="billing"]').click();await page.locator("#last-receipt").click();
  await expect(page.locator("#receipt-preview .net")).toHaveText("TOTAL₹252.00");
  await page.locator("#receipt-dialog [data-close]").click();
  await page.locator('[data-nav="sales"]').click();await expect(page.locator("#sales-list tbody tr")).toHaveCount(2);
});
