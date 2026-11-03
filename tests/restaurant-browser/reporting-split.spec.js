import { test, expect } from "@playwright/test";
import { unlockInclusiveFixture as unlockFixture } from "./access-helper.js";
import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import ExcelJS from "exceljs";
import { setup, order, MemoryImages } from "../restaurant/helpers.js";
import { createBackup } from "../../restaurant/backup.js";

const artifacts = resolve("test-results/restaurant-artifacts");
mkdirSync(artifacts, { recursive: true });
test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-10-30T04:00:00.000Z"));
});
async function ready(page) {
  await page.goto("/");
  await unlockFixture(page);
  await expect(page.locator("#storage-status")).toHaveText("Browser preview · SQLite");
  await expect(page.locator(".product-tile")).toHaveCount(36);
}
async function closeReceipt(page) {
  await page.locator("#receipt-dialog [data-close]").click();
  await expect(page.locator("#receipt-dialog")).not.toBeVisible();
}
async function sell(page, { product = "menu-001", method = "CASH", split = false } = {}) {
  await page.locator(`[data-product-id="${product}"]`).click();
  await page.locator("#pay-button").click();
  if (split) {
    await page.locator("#split-payment").click();
    await page.locator("#cash-tender").fill("50.00");
    await page.locator("#upi-received").fill("100.00");
  } else await page.locator("#payment-method").selectOption(method);
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.locator("#complete-sale").evaluate((button) => { button.click(); button.click(); });
  await expect(page.locator("#receipt-dialog")).toBeVisible();
}
async function totals(page, prefix, expected) {
  for (const [key, value] of Object.entries(expected))
    await expect(page.locator(`${prefix} [data-total="${key}"] strong`)).toHaveText(value);
}

test("SPLIT-UI-01 cash, GPay, cancelled and mixed bills reconcile, reprint, return and restore", async ({ page, context }) => {
  const errors = [], external = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    if (!request.url().startsWith("http://127.0.0.1:5175") && !request.url().startsWith("data:")) external.push(request.url());
  });
  await ready(page);
  await context.setOffline(true);
  await sell(page);
  await closeReceipt(page);
  await sell(page, { method: "UPI" });
  await closeReceipt(page);
  await sell(page);
  await page.locator("#correct-bill").click();
  await page.locator('#correction-form [name="kind"]').selectOption("void");
  await page.locator('#correction-form [name="reason"]').fill("Cancelled test bill");
  await page.locator("#correction-form .button-primary").click();
  await expect(page.locator("#correction-dialog")).not.toBeVisible();
  await closeReceipt(page);
  // Seeded EGG BIRIYANI 1/2 KG is independently priced at ₹150.
  await sell(page, { product: "menu-034", split: true });
  await expect(page.locator("#receipt-preview")).toContainText("Cash: ₹50.00");
  await expect(page.locator("#receipt-preview")).toContainText("GPay (UPI): ₹100.00");
  await expect(page.locator("#receipt-preview")).toContainText("000004");
  const receipt = await page.locator("#receipt-preview").innerText();
  await closeReceipt(page);
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(4);
  const expected = { bills: "4", sales_paise: "₹660.00", corrections_paise: "₹170.00", net_paise: "₹490.00", cash_paise: "₹220.00", upi_paise: "₹270.00" };
  await totals(page, "#sales-totals", expected);
  await page.locator('#sales-filter [name="method"]').selectOption("cash");
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(3);
  await totals(page, "#sales-totals", { net_paise: "₹220.00", upi_paise: "₹0.00" });
  await page.locator('#sales-filter [name="method"]').selectOption("upi");
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(2);
  await totals(page, "#sales-totals", { net_paise: "₹270.00", cash_paise: "₹0.00" });
  await page.locator('#sales-filter [name="search"]').fill("000004");
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(1);
  await page.locator("[data-view-sale]").click();
  expect(await page.locator("#receipt-preview").innerText()).toBe(receipt);
  await closeReceipt(page);
  await page.locator('[data-nav="reports"]').click();
  await totals(page, "#report-totals", expected);
  await page.locator('[data-report-tab="payments"]').click();
  await expect(page.locator("#report-details")).toContainText("₹220.00");
  await expect(page.locator("#report-details")).toContainText("₹270.00");
  await page.locator('[data-report-tab="cancelled"]').click();
  await expect(page.locator("#report-details")).toContainText("Cancelled test bill");
  await page.locator('#report-filter [name="method"]').selectOption("upi");
  // A browser needs localhost to load lazy bundled chunks; Android reads these
  // from its installed assets. External requests remain forbidden below.
  await context.setOffline(false);
  const downloadWait = page.waitForEvent("download");
  await page.locator('[data-export="xlsx"]').click();
  const file = resolve(artifacts, "split-upi.xlsx");
  await (await downloadWait).saveAs(file);
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(file);
  expect(workbook.getWorksheet("Invoices").rowCount).toBe(3);
  expect(workbook.getWorksheet("Items").rowCount).toBe(3);
  await page.locator('[data-nav="sales"]').click();
  await page.locator("[data-correct-sale]").click();
  await expect(page.locator("#return-channels")).toBeVisible();
  await page.locator('#correction-form [name="amount"]').fill("30.00");
  await page.locator('#correction-form [name="cash_return"]').fill("10.00");
  await page.locator('#correction-form [name="upi_return"]').fill("15.00");
  await page.locator('#correction-form [name="reason"]').fill("Actual mixed return");
  await page.locator("#correction-form .button-primary").click();
  await expect(page.locator("#correction-error")).toContainText("shares must equal");
  await page.locator('#correction-form [name="upi_return"]').fill("20.00");
  await page.locator("#correction-form .button-primary").click();
  await expect(page.locator("#correction-dialog")).not.toBeVisible();
  await closeReceipt(page);
  await page.locator('[data-nav="reports"]').click();
  await page.locator('#report-filter [name="method"]').selectOption("all");
  await totals(page, "#report-totals", { net_paise: "₹460.00", cash_paise: "₹210.00", upi_paise: "₹250.00", corrections_paise: "₹200.00" });
  await page.locator('[data-nav="settings"]').click();
  const backupWait = page.waitForEvent("download");
  await page.locator("#backup-button").click();
  const backup = resolve(artifacts, "split-backup.json");
  await (await backupWait).saveAs(backup);
  const saved = JSON.parse(JSON.parse(readFileSync(backup, "utf8")).payload).tables;
  expect(saved.sales).toHaveLength(4);
  expect(saved.payments).toHaveLength(5);
  expect(saved.adjustments).toHaveLength(2);
  expect(saved.adjustment_payments).toHaveLength(3);
  await context.setOffline(false);
  await page.locator("#restore-file").setInputFiles(backup);
  await expect(page.locator("#restore-dialog")).toBeVisible();
  await page.locator("#restore-confirm").fill("RESTORE");
  await page.locator("#restore-button").click();
  await expect(page.locator("#storage-status")).toHaveText("Browser preview · SQLite");
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(4);
  await totals(page, "#sales-totals", { net_paise: "₹460.00", cash_paise: "₹210.00", upi_paise: "₹250.00" });
  await page.locator('[data-nav="billing"]').click();
  await sell(page);
  await expect(page.locator("#receipt-preview")).toContainText("000005");
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test("APP-INIT-01 independent dates/payment defaults, separated screens and bilingual dashboard", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (["warning", "error"].includes(message.type())) errors.push(message.text());
  });
  await ready(page);
  for (const [screen, from] of [["dashboard", "2026-10-30"], ["sales", "2026-10-30"], ["reports", "2026-10-01"]]) {
    await page.locator(`[data-nav="${screen}"]`).click();
    const form = page.locator(`#${screen === "reports" ? "report" : screen}-filter`);
    await expect(form.locator('[name="from"]')).toHaveValue(from);
    await expect(form.locator('[name="to"]')).toHaveValue("2026-10-30");
    await expect(form.locator('[name="method"]')).toHaveValue("all");
    await expect(page.locator('[data-export]:visible')).toHaveCount(screen === "reports" ? 3 : 0);
    await form.locator('[name="method"]').selectOption("upi");
    await form.locator('[data-preset="yesterday"]').click();
    await expect(form.locator('[name="from"]')).toHaveValue("2026-10-29");
    await expect(form.locator('[name="to"]')).toHaveValue("2026-10-29");
    await form.locator('[data-preset="week"]').click();
    await expect(form.locator('[name="from"]')).toHaveValue("2026-10-26");
    await form.locator('[data-preset="custom"]').click();
    await expect(form.locator('[name="from"]')).toBeFocused();
  }
  await page.locator('[data-nav="dashboard"]').click();
  await expect(page.locator('#dashboard-filter [name="method"]')).toHaveValue("upi");
  await expect(page.locator('#dashboard-metrics [lang="ta"]')).toHaveCount(6);
  await expect(page.locator('#dashboard-period-revenue [lang="ta"]')).toHaveCount(2);
  await expect(page.locator('[data-view="dashboard"]')).toContainText("இறுதி விற்பனை");
  await expect(page.locator('#sales-list:visible')).toHaveCount(0);
  await page.screenshot({ path: resolve(artifacts, "dashboard-tamil.png") });
  expect(errors).toEqual([]);
});

test("DASH-UI-02 the original dashboard limits recent bills and top items to five", async ({ page }) => {
  const { ledger, db } = await setup({ now: () => "2026-10-30T04:00:00.000Z" });
  let backup;
  try {
    const products = (await ledger.products()).slice(0, 7);
    for (const p of products) await ledger.checkout(order({
      items: [{ product_id: p.id, name: p.name, portion: p.portion, unit_paise: p.price_paise, quantity: 1 }],
      tendered_paise: p.price_paise,
    }));
    backup = await createBackup(ledger, new MemoryImages());
  } finally { await db.close(); }
  await ready(page);
  await page.locator('[data-nav="settings"]').click();
  await page.locator("#restore-file").setInputFiles({ name: "dashboard.json", mimeType: "application/json", buffer: Buffer.from(backup) });
  await expect(page.locator("#restore-dialog")).toBeVisible();
  await page.locator("#restore-confirm").fill("RESTORE");
  await page.locator("#restore-button").click();
  await expect(page.locator("#storage-status")).toHaveText("Browser preview · SQLite");
  await page.locator('[data-nav="dashboard"]').click();
  await expect(page.locator('[data-metric="bills"] .metric-value')).toHaveText("7");
  await expect(page.locator("#recent-sales tr")).toHaveCount(5);
  await expect(page.locator("#recent-sales tr").first()).toContainText("000007");
  await expect(page.locator("#top-products .dashboard-ranked-item")).toHaveCount(5);
  await page.locator("#recent-sales button").first().click();
  await expect(page.locator("#receipt-preview")).toContainText("000007");
  await closeReceipt(page);
  await page.screenshot({ path: resolve(artifacts, "dashboard-sales.png"), fullPage: true });
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(7);
});

for (const [width, height] of [[1920, 1080], [1280, 720], [1024, 768]]) {
  test(`TOUCH-UI-01 ${width}x${height} categories, four cart rows and customer form fit`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await ready(page);
    for (const id of ["menu-001", "menu-002", "menu-003", "menu-004"])
      await page.locator(`[data-product-id="${id}"]`).click();
    await expect(page.locator("#cart-count")).toHaveText("4");
    await expect(page.locator("#pay-button")).toBeEnabled();
    const geometry = await page.evaluate(() => {
      const rect = (selector) => document.querySelector(selector).getBoundingClientRect();
      const cart = rect("#cart-lines");
      const rows = [...document.querySelectorAll(".cart-line")].map((e) => e.getBoundingClientRect());
      const actions = [...document.querySelectorAll(".cart-touch-actions button, .cart-line button, .category-strip button, #pay-button, #add-billing-customer")].map((e) => ({ name: e.getAttribute("aria-label") || e.textContent, w: e.getBoundingClientRect().width, h: e.getBoundingClientRect().height }));
      return { scroll: document.documentElement.scrollWidth, rows: rows.filter((r) => r.top >= cart.top && r.bottom <= cart.bottom).length, categories: rect(".category-strip").right, actions };
    });
    expect(geometry.scroll).toBeLessThanOrEqual(width);
    expect(geometry.rows).toBeGreaterThanOrEqual(3);
    expect(geometry.categories).toBeLessThanOrEqual(width);
    expect(geometry.actions.filter((a) => a.w < 44 || a.h < 44)).toEqual([]);
    await page.screenshot({ path: resolve(artifacts, `billing-touch-${width}.png`) });
    await page.locator("#add-billing-customer").click();
    await expect(page.locator('#customer-form input:not([type="hidden"])')).toHaveCount(3);
    const fields = await page.locator('#customer-form input:not([type="hidden"])').evaluateAll((inputs) => inputs.map((input) => { const r = input.getBoundingClientRect(); return { left: r.left, width: r.width, height: r.height }; }));
    expect(new Set(fields.map((f) => f.left)).size).toBe(1);
    expect(new Set(fields.map((f) => f.width)).size).toBe(1);
    expect(fields.every((f) => f.height >= 44)).toBe(true);
    await page.screenshot({ path: resolve(artifacts, `customer-touch-${width}.png`) });
  });
}
