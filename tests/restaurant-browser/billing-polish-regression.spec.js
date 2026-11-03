import { test, expect } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { unlockFixture } from "./access-helper.js";
import { inspectBackup } from "../../restaurant/backup.js";
import { database } from "../restaurant/helpers.js";

const output = resolve("test-results/startup-polish");
mkdirSync(output, { recursive: true });
const required = ["menu-027", "menu-028", "menu-017", "menu-004"];
const cases = [
  { name: "required-405", ids: required, discount: "0.00", round: false, values: ["405.00","0.00","405.00","10.12","10.13","0.00","425.25"] },
  { name: "discount-20", ids: required, discount: "20.00", round: false, values: ["405.00","20.00","385.00","9.61","9.64","0.00","404.25"] },
  { name: "fixed-half-kg-portion", ids: ["menu-030"], discount: "0.00", round: false, values: ["160.00","0.00","160.00","4.00","4.00","0.00","168.00"] },
  { name: "round-on", ids: required, discount: "0.00", round: true, values: ["405.00","0.00","405.00","10.12","10.13","-0.25","425.00"] },
];

test("BILLING-REGRESSION-405 exact before/after screen, saved/printed/reprinted receipts, reports and complete restore", async ({ page }) => {
  test.setTimeout(90000);
  await page.clock.setFixedTime(new Date("2026-11-03T05:00:00.000Z"));
  await page.goto("/");
  await unlockFixture(page);
  await expect(page.locator("#access-recover")).toBeEnabled();
  const result = [];
  for (const scenario of cases) {
    await page.locator('[data-nav="settings"]').click();
    await page.locator('#settings-form [name="round_rupee"]').setChecked(scenario.round);
    await page.locator('#settings-form .button-primary').click();
    await expect(page.locator('#settings-form .button-primary')).toBeEnabled();
    await page.locator('[data-nav="billing"]').click();
    for (const id of scenario.ids) await page.locator(`[data-product-id="${id}"]`).click();
    await page.locator("#order-discount").fill(scenario.discount);
    for (const [index, name] of ["gross","discount","taxable","cgst","sgst","round","net"].entries()) {
      const text = scenario.values[index].startsWith("-") ? `-₹${scenario.values[index].slice(1)}` : `₹${scenario.values[index]}`;
      await expect(page.locator(`#total-${name}`)).toHaveText(text);
    }
    await page.locator("#pay-button").click();
    await page.locator("#complete-sale").click();
    const receipt = page.locator("#receipt-preview .receipt-paper");
    await expect(receipt.locator(".net")).toHaveText(`TOTAL₹${scenario.values[6]}`);
    for (const [key,index] of [["discount",1],["taxable",2],["cgst",3],["sgst",4],["round",5]])
      await expect(receipt.locator(`[data-receipt-total="${key}"]`)).toContainText(`₹${scenario.values[index]}`);
    const html = await receipt.innerHTML();
    await page.evaluate(() => { window.print = () => {}; });
    await page.locator("#print-receipt").click();
    await expect(page.locator("#print-status")).toContainText("Print submitted");
    expect(await page.locator("#print-document .receipt-paper").innerHTML()).toBe(html);
    await page.locator("#receipt-dialog [data-close]").click();
    await page.locator("#last-receipt").click();
    await expect(receipt).toBeVisible();
    expect(await receipt.innerHTML()).toBe(html);
    result.push({ name: scenario.name, values: scenario.values, receipt: await receipt.textContent() });
    await page.locator("#receipt-dialog [data-close]").click();
  }
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(4);
  await expect(page.locator('#sales-totals [data-total="sales_paise"] strong')).toHaveText("₹1422.50");
  await page.locator('[data-nav="reports"]').click();
  await expect(page.locator('#report-totals [data-total="sales_paise"] strong')).toHaveText("₹1422.50");
  await page.locator('[data-nav="settings"]').click();
  const backupPath = resolve(output, `billing-${process.env.BILLING_PHASE || "current"}.json`);
  const download = page.waitForEvent("download");
  await page.locator("#backup-button").click();
  await (await download).saveAs(backupPath);
  const backup = await inspectBackup(readFileSync(backupPath,"utf8"), () => database());
  expect(backup.tables.sales.map(sale => sale.total_paise)).toEqual([42525,40425,16800,42500]);
  expect(backup.tables.sales.map(sale => sale.round_paise)).toEqual([0,0,0,-25]);
  expect(backup.tables.payments.map(payment => payment.amount_paise)).toEqual([42525,40425,16800,42500]);
  await page.locator("#restore-file").setInputFiles(backupPath);
  await expect(page.locator("#restore-dialog")).toBeVisible();
  await page.locator("#restore-confirm").fill("RESTORE");
  const reload = page.waitForEvent("load");
  await page.locator("#restore-button").click();
  await reload;
  await expect(page.locator("#access-screen")).toBeHidden();
  await expect(page.locator("#access-recover")).toBeEnabled();
  await page.locator('[data-nav="settings"]').click();
  const again = page.waitForEvent("download");
  await page.locator("#backup-button").click();
  const restoredPath = resolve(output,"billing-restored.json");
  await (await again).saveAs(restoredPath);
  const restored = await inspectBackup(readFileSync(restoredPath,"utf8"), () => database());
  expect(restored.tables).toEqual(backup.tables);
  expect(restored.files).toEqual(backup.files);
  writeFileSync(resolve(output,`billing-${process.env.BILLING_PHASE || "current"}-results.json`), JSON.stringify(result,null,2));
});
