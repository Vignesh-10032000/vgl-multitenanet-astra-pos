import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { unlockFixture } from "./access-helper.js";
import { database, setup, order, menu } from "../restaurant/helpers.js";
import { V2_TABLES } from "../../restaurant/schema.js";
import { inspectBackup } from "../../restaurant/backup.js";

const output = resolve("test-results/gst-exclusive-2026-11-02");
mkdirSync(output, { recursive: true });

test("GST-EXCLUSIVE-UI-01 fresh menu adds GST through cash/split payments, saved receipts, reload and backup", async ({ page, context }) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await context.route(/https?:\/\/(?!127\.0\.0\.1:5175)/, route => route.abort());
  await page.clock.setFixedTime(new Date("2026-11-02T05:00:00.000Z"));
  await page.goto("/"); await unlockFixture(page);
  const tile = page.locator('.product-tile[data-product-id="menu-001"]');
  await expect(tile).toContainText("₹170.00");
  await expect(page.locator("#scanner-status")).toContainText("Menu prices + GST");
  await tile.click();
  await expect(page.locator("#total-gross")).toHaveText("₹170.00");
  await expect(page.locator("#total-taxable")).toHaveText("₹170.00");
  await expect(page.locator("#total-cgst")).toHaveText("₹4.25");
  await expect(page.locator("#total-sgst")).toHaveText("₹4.25");
  await expect(page.locator("#total-net")).toHaveText("₹178.50");
  await page.locator("#order-discount").fill("10.00");
  await expect(page.locator("#total-net")).toHaveText("₹168.00");
  await page.locator("#order-discount").fill("0.00");
  await expect(page.locator("#total-net")).toHaveText("₹178.50");
  await page.screenshot({ path: resolve(output, "billing-170-plus-gst.png") });
  await page.locator("#pay-button").click();
  await page.locator("#cash-tender").fill("200.00");
  await expect(page.locator("#payment-change")).toHaveText("₹21.50");
  await page.locator("#complete-sale").click();
  const receipt = page.locator("#receipt-preview .receipt-paper");
  await expect(receipt).toContainText("GST added to menu prices");
  await expect(receipt).toContainText("CGST 2.5%: ₹4.25");
  await expect(receipt.locator(".net")).toHaveText("TOTAL₹178.50");
  await receipt.screenshot({ path: resolve(output, "receipt-170-plus-gst.png") });
  const receiptHTML = await receipt.innerHTML();
  await page.evaluate(() => { window.print = () => {}; });
  await page.locator("#print-receipt").click();
  await page.emulateMedia({ media: "print" });
  const printPaper = page.locator("#print-document .receipt-paper");
  await expect(printPaper).toBeVisible();
  const bounds = await printPaper.boundingBox();
  expect(await printPaper.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(false);
  await page.pdf({ path: resolve(output, "receipt-170-plus-gst-80mm.pdf"), width: "80mm", height: `${(bounds.height + 2) / 96 * 25.4}mm`, printBackground: true });
  await page.emulateMedia({ media: "screen" });
  await page.locator("#receipt-dialog [data-close]").click();
  await page.reload();
  await page.locator("#last-receipt").click();
  await expect(receipt).toBeVisible();
  expect(await receipt.innerHTML()).toBe(receiptHTML);
  await page.locator("#receipt-dialog [data-close]").click();
  await tile.click(); await tile.click();
  await expect(page.locator("#total-net")).toHaveText("₹357.00");
  await page.locator("#pay-button").click();
  await page.locator("#split-payment").click();
  await page.locator("#upi-received").fill("257.00");
  await page.locator("#cash-tender").fill("100.00");
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.locator("#complete-sale").click();
  await expect(receipt.locator(".net")).toHaveText("TOTAL₹357.00");
  await page.locator("#receipt-dialog [data-close]").click();
  await page.locator('[data-nav="settings"]').click();
  await expect(page.locator('#settings-form [name="tax_inclusive"]')).toHaveValue("false");
  const downloadEvent = page.waitForEvent("download");
  await page.locator("#backup-button").click();
  const download = await downloadEvent, path = resolve(output, "exclusive-backup.json");
  await download.saveAs(path);
  const backup = await inspectBackup(readFileSync(path, "utf8"), () => database());
  expect(backup.tables.sales.map(sale => sale.total_paise)).toEqual([17850, 35700]);
  expect(backup.tables.sales.every(sale => sale.tax_inclusive === 0)).toBe(true);
  expect(backup.tables.payments.reduce((sum, row) => sum + row.amount_paise, 0)).toBe(53550);
  await page.locator('#settings-form [name="tax_inclusive"]').selectOption("true");
  await page.locator('#settings-form .button-primary').click();
  await page.getByText("Setup saved locally", { exact: true }).waitFor();
  await page.locator('[data-nav="billing"]').click();
  await tile.click();
  await expect(page.locator("#total-net")).toHaveText("₹170.00");
  await page.locator("#last-receipt").click();
  await expect(receipt.locator(".net")).toHaveText("TOTAL₹357.00");
  expect(errors).toEqual([]);
});

test("GST-EXCLUSIVE-UI-02 WASM upgrades a real v2 database while preserving old bill and issuing the next number with added GST", async ({ page }, testInfo) => {
  const fixture = await setup({ now: () => "2026-11-02T05:00:00.000Z" });
  let snapshot;
  try { await fixture.ledger.checkout(order()); snapshot = await fixture.ledger.snapshot(); }
  finally { await fixture.db.close(); }
  const path = testInfo.outputPath("version-2.sqlite"), db = database(path);
  try {
    await db.exec(readFileSync(new URL("../restaurant/fixtures/schema-v2.sql", import.meta.url), "utf8"));
    await db.run("INSERT INTO schema_versions VALUES(2)");
    for (const [name, columns] of Object.entries(V2_TABLES)) for (const row of snapshot[name]) {
      if (name === "settings" || name === "sales") {
        const field = name === "settings" ? "value" : "identity", value = JSON.parse(row[field]);
        delete value.tax_inclusive; delete value.gst_pricing_revision;
        row[field] = JSON.stringify(value);
      }
      await db.run(`INSERT INTO ${name}(${columns.join(",")}) VALUES(${columns.map(() => "?").join(",")})`, columns.map(column => row[column]));
    }
  } finally { await db.close(); }
  await page.clock.setFixedTime(new Date("2026-11-02T05:00:00.000Z"));
  await page.goto("/");
  await expect(page.locator("#access-submit")).toBeEnabled();
  await page.evaluate(async bytes => {
    await new Promise((resolve, reject) => {
      const request = indexedDB.open("keyval-store");
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const database = request.result, transaction = database.transaction("keyval", "readwrite");
        transaction.objectStore("keyval").put(new Uint8Array(bytes), "restaurant-sqlite-v1");
        transaction.oncomplete = () => { database.close(); resolve(); };
        transaction.onerror = () => reject(transaction.error);
      };
    });
  }, [...readFileSync(path)]);
  await page.reload(); await unlockFixture(page);
  await page.locator("#last-receipt").click();
  const receipt = page.locator("#receipt-preview .receipt-paper");
  await expect(receipt.locator(".net")).toHaveText("TOTAL₹170.00");
  await expect(receipt).toContainText("CGST 2.5%: ₹4.05");
  await expect(receipt).not.toContainText("GST added to menu prices");
  await page.locator("#receipt-dialog [data-close]").click();
  await page.locator(`[data-product-id="${menu.items[0].reference_id}"]`).click();
  await expect(page.locator("#total-net")).toHaveText("₹178.50");
  await page.locator("#pay-button").click(); await page.locator("#complete-sale").click();
  await expect(receipt).toContainText("000002");
  await expect(receipt.locator(".net")).toHaveText("TOTAL₹178.50");
});
