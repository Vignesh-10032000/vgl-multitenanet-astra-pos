import { test, expect } from "@playwright/test";
import { unlockInclusiveFixture as unlockFixture } from "./access-helper.js";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";
import ExcelJS from "exceljs";
import { setup, order, MemoryImages } from "../restaurant/helpers.js";
import { createBackup } from "../../restaurant/backup.js";

test("GSTIN and included CGST 2.5 / SGST 2.5 appear in billing, saved receipt and reprint", async ({
  page,
}) => {
  await ready(page);
  await expect(page.locator("#mode-label")).toHaveText("Receipt: Tax invoice");
  await page.locator('[data-nav="settings"]').click();
  await expect(page.locator('#settings-form [name="gstin"]')).toHaveValue(
    "33BPFPD3960P2ZN",
  );
  await expect(page.locator('#settings-form [name="tax_percent"]')).toHaveValue(
    "5.00",
  );
  await page.locator('[data-nav="billing"]').click();
  await page.locator('[data-product-id="menu-001"]').click();
  await expect(page.locator("#cgst-label")).toHaveText("CGST 2.5%");
  await expect(page.locator("#sgst-label")).toHaveText("SGST 2.5%");
  await expect(page.locator("#total-taxable")).toHaveText("₹161.90");
  await expect(page.locator("#total-cgst")).toHaveText("₹4.05");
  await expect(page.locator("#total-sgst")).toHaveText("₹4.05");
  await expect(page.locator("#total-net")).toHaveText("₹170.00");
  await page.locator("#pay-button").click();
  await page.locator("#cash-tender").fill("200.00");
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-dialog")).toBeVisible();
  await expect(page.locator("#receipt-preview")).toContainText(
    "GSTIN: 33BPFPD3960P2ZN",
  );
  await expect(page.locator("#receipt-preview")).toContainText(
    "CGST 2.5%: ₹4.05",
  );
  await expect(page.locator("#receipt-preview")).toContainText(
    "SGST 2.5%: ₹4.05",
  );
  await expect(page.locator("#receipt-preview")).not.toContainText(
    "TRAINING —",
  );
  await page
    .locator("#receipt-preview .receipt-paper")
    .screenshot({ path: resolve(artifacts, "gst-receipt.png") });
  await page.locator("#receipt-dialog [data-close]").click();
  await page.reload();
  await page.locator("#last-receipt").click();
  await expect(page.locator("#receipt-preview")).toContainText(
    "CGST 2.5%: ₹4.05",
  );
  await expect(page.locator("#receipt-preview")).toContainText(
    "GSTIN: 33BPFPD3960P2ZN",
  );
});
const root = resolve(import.meta.dirname, "../..");
const artifacts = resolve(root, "test-results/restaurant-artifacts");
mkdirSync(artifacts, { recursive: true });
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aV1sAAAAASUVORK5CYII=",
  "base64",
);
async function ready(page) {
  await page.goto("/");
  await unlockFixture(page);
  await expect(page.locator(".product-tile")).toHaveCount(36);
}
async function sell(page, { method = "cash", tender = "200.00" } = {}) {
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator("#pay-button").click();
  await page.locator("#payment-method").selectOption(method.toUpperCase());
  if (method === "cash") await page.locator("#cash-tender").fill(tender);
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-dialog")).toBeVisible();
}
test("touch billing retains original panel arrangement at 1920x1080 without stock or desktop shortcut chrome", async ({
  page,
}) => {
  await ready(page);
  const bounds = async () =>
    page.evaluate(() =>
      Object.fromEntries(
        [".pos-workspace", ".product-browser", ".cart-panel"].map((s) => {
          const r = document.querySelector(s).getBoundingClientRect();
          return [s, { x: r.x, y: r.y, width: r.width, height: r.height }];
        }),
      ),
    );
  const actual = await bounds();
  await page.screenshot({ path: resolve(artifacts, "billing-1920.png") });
  const visible = await page.locator("body").innerText();
  expect(visible).not.toMatch(/stock|inventory|tenant|supplier|landing page/i);
  expect(actual[".product-browser"].x).toBeLessThan(actual[".cart-panel"].x);
  expect(actual[".cart-panel"].x + actual[".cart-panel"].width).toBeLessThanOrEqual(1920);
  expect(actual[".cart-panel"].y + actual[".cart-panel"].height).toBeLessThanOrEqual(1080);
  await expect(page.locator(".shortcut-strip, #configure-quick-keys")).toHaveCount(0);

});
test("cash and GPay bills save, restart recovers ledger, filters reconcile; no external requests", async ({
  page,
  context,
}) => {
  const external = [];
  page.on("request", (r) => {
    if (
      !r.url().startsWith("http://127.0.0.1:5175") &&
      !r.url().startsWith("data:")
    )
      external.push(r.url());
  });
  await ready(page);
  await context.setOffline(true);
  await sell(page);
  await expect(page.locator("#receipt-preview")).toContainText(
    "Change: ₹30.00",
  );
  await expect(page.locator("#receipt-preview")).toContainText("000001");
  await page.locator("#receipt-dialog [data-close]").click();
  await sell(page, { method: "upi" });
  await expect(page.locator("#receipt-preview")).toContainText("GPay (UPI)");
  await expect(page.locator("#receipt-preview")).toContainText("000002");
  await page.locator("#receipt-dialog [data-close]").click();
  await context.setOffline(false);
  await page.reload();
  await expect(page.locator(".product-tile")).toHaveCount(36);
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(2);
  await expect(page.locator("#sales-totals")).toContainText("₹340.00");
  await page.locator("#sales-filter select").selectOption("upi");
  await page.locator('#sales-filter button[type="submit"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(1);
  await expect(page.locator("#sales-list")).toContainText("GPay (UPI)");
  expect(external).toEqual([]);
});
test("local product photograph, independent price, Tamil customer and draft survive reload", async ({
  page,
  browser,
}) => {
  await ready(page);
  await page.locator('[data-nav="products"]').click();
  await page.locator("#add-product").click();
  const f = page.locator("#product-form");
  await f.locator('[name="name"]').fill("சிக்கன் சிறப்பு");
  await f.locator('[name="portion"]').fill("Half");
  await f.locator('[name="category"]').fill("Special");
  await f.locator('[name="price"]').fill("230.01");
  await f
    .locator('[name="photo"]')
    .setInputFiles({ name: "dish.png", mimeType: "image/png", buffer: png });
  await f.getByRole("button", { name: "Save product" }).click();
  await expect(page.locator("#product-dialog")).not.toBeVisible();
  await page.locator('[data-nav="customers"]').click();
  await page.locator("#add-customer").click();
  const c = page.locator("#customer-form");
  expect(await c.locator('input:not([type="hidden"])').count()).toBe(3);
  await c.locator('[name="name"]').fill("பிரியா");
  await c.locator('[name="phone"]').fill("9999999999");
  await c.locator('[name="city"]').fill("Pollachi");
  await c.getByRole("button", { name: "Save customer" }).click();
  await expect(page.locator("#customer-dialog")).not.toBeVisible();
  await page.locator('[data-nav="billing"]').click();
  await page.locator("#pos-search").fill("சிக்கன்");
  const tile = page.locator(".product-tile");
  await expect(tile).toHaveCount(1);
  await expect(tile.locator("img")).toHaveAttribute(
    "src",
    /^data:image\/jpeg;base64,/,
  );
  await tile.click();
  await expect(page.locator("#draft-status")).toContainText(
    "Cart saved locally",
  );
  await page.reload();
  await expect(page.locator("#cart-lines")).toContainText("சிக்கன் சிறப்பு");
  await expect(page.locator("#total-net")).toHaveText("₹230.01");
  await page.locator("#pos-search").fill("சிக்கன்");
  await expect(page.locator(".product-tile")).toHaveCount(1);
  await expect(page.locator(".product-tile img")).toHaveAttribute(
    "src",
    /^data:image\/jpeg;base64,/,
  );
  await expect(page.locator("#pos-customer")).toContainText("பிரியா");
  await page.locator('[data-nav="settings"]').click();
  const downloadWait = page.waitForEvent("download");
  await page.locator("#backup-button").click();
  const download = await downloadWait;
  const backup = resolve(artifacts, "photo-backup.json");
  await download.saveAs(backup);
  const saved = JSON.parse(JSON.parse(readFileSync(backup, "utf8")).payload);
  expect(Object.keys(saved.files)).toHaveLength(24); // 22 starter photos, own dish and owner logo.
  const savedSettings = JSON.parse(saved.tables.settings.find(row => row.id === "store").value);
  expect(saved.files[savedSettings.logo]).toMatch(/^data:image\/jpeg;base64,/);
  const ownProduct = saved.tables.products.find(product => product.name === "சிக்கன் சிறப்பு");
  expect(saved.files[ownProduct.image]).toMatch(/^data:image\/jpeg;base64,/);
  const restored = await browser.newContext({
    baseURL: "http://127.0.0.1:5175",
  });
  try {
    const target = await restored.newPage();
    await ready(target);
    await target.locator('[data-nav="settings"]').click();
    await target.locator("#restore-file").setInputFiles(backup);
    await expect(target.locator("#restore-dialog")).toBeVisible();
    await target.locator("#restore-confirm").fill("RESTORE");
    await target.locator("#restore-button").click();
    await expect(target.locator("#storage-status")).toContainText("SQLite");
    await target.locator('[data-nav="billing"]').click();
    await target.locator("#pos-search").fill("சிக்கன்");
    await expect(target.locator(".product-tile")).toHaveCount(1);
    await expect(target.locator(".product-tile img")).toHaveAttribute(
      "src",
      /^data:image\/jpeg;base64,/,
    );
    await expect(target.locator("#total-net")).toHaveText("₹230.01");
  } finally {
    await restored.close();
  }
});
test("offline CSV/XLSX/PDF exports and backup downloads are parseable; restore validates in WASM", async ({
  page,
}) => {
  await ready(page);
  await page.locator('[data-nav="customers"]').click();
  await page.locator("#add-customer").click();
  await page.locator('#customer-form [name="name"]').fill('=SUM(1,2) "தமிழ்"');
  await page.locator('#customer-form [name="city"]').fill("Pollachi");
  await page.locator("#customer-form .button-primary").click();
  await expect(page.locator("#customer-dialog")).not.toBeVisible();
  await page.locator('[data-nav="billing"]').click();
  await page
    .locator("#pos-customer")
    .selectOption({ label: '=SUM(1,2) "தமிழ்"' });
  await sell(page);
  await page.locator("#correct-bill").click();
  await page.locator('#correction-form [name="amount"]').fill("20.00");
  await page.locator('#correction-form [name="reason"]').fill("Refund test");
  await page.locator("#correction-form .button-primary").click();
  await expect(page.locator("#correction-dialog")).not.toBeVisible();
  await page.locator("#receipt-dialog [data-close]").click();
  await page.locator('[data-nav="reports"]').click();
  await expect(page.locator("#report-totals")).toContainText("₹150.00");
  for (const format of ["csv", "xlsx", "pdf"]) {
    const wait = page.waitForEvent("download");
    await page.locator(`[data-export="${format}"]`).click();
    const download = await wait;
    const path = resolve(artifacts, `auditor.${format}`);
    await download.saveAs(path);
    expect(readFileSync(path).length).toBeGreaterThan(500);
  }
  const workbook = new ExcelJS.Workbook();
  await workbook.xlsx.readFile(resolve(artifacts, "auditor.xlsx"));
  expect(workbook.getWorksheet("Invoices").getCell("K2").value).toBe(170);
  expect(workbook.getWorksheet("Corrections").getCell("F2").value).toBe(20);
  expect(workbook.getWorksheet("Invoices").getCell("C2").value).toBe(
    '\'=SUM(1,2) "தமிழ்"',
  );
  expect(
    readFileSync(resolve(artifacts, "auditor.pdf")).subarray(0, 8).toString(),
  ).toBe("%PDF-1.4");
  await page.locator('[data-nav="settings"]').click();
  const wait = page.waitForEvent("download");
  await page.locator("#backup-button").click();
  const download = await wait;
  const path = resolve(artifacts, "backup.json");
  await download.saveAs(path);
  const saved = JSON.parse(JSON.parse(readFileSync(path, "utf8")).payload);
  expect(saved.tables.sales.length).toBe(1);
  await page.locator("#restore-file").setInputFiles(path);
  await expect(page.locator("#restore-dialog")).toBeVisible();
  await expect(page.locator("#restore-summary")).toContainText("1 bills");
  await page.locator("#restore-confirm").fill("RESTORE");
  await page.locator("#restore-button").click();
  await expect(page.locator("#storage-status")).toContainText("SQLite");
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(1);
});
test("OnePlus-sized portrait layout has usable menu and checkout without horizontal overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 412, height: 915 });
  await ready(page);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(412);
  expect(
    await page
      .locator(".side-nav nav a")
      .evaluateAll((links) =>
        links.every(
          (a) =>
            a.querySelector("span").getBoundingClientRect().width <=
            a.getBoundingClientRect().width,
        ),
      ),
  ).toBe(true);
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator("#pay-button").scrollIntoViewIfNeeded();
  await page.locator("#pay-button").click();
  await expect(page.locator("#payment-dialog")).toBeVisible();
  await page.screenshot({ path: resolve(artifacts, "phone-payment.png") });
});
test("older WebView helper absence is supported; multi-page monthly exports include Tamil and cross-month adjustments", async ({
  page,
}) => {
  // Keep the browser's month aligned with this intentionally October-only ledger.
  await page.clock.setFixedTime(new Date("2026-10-31T04:00:00.000Z"));
  await page.addInitScript(() => {
    crypto.randomUUID = undefined;
    window.structuredClone = undefined;
  });
  let now = "2026-09-30T18:29:59.999Z";
  const { ledger, db } = await setup({ now: () => now });
  const prior = await ledger.checkout(order());
  now = "2026-09-30T18:30:00.000Z";
  const customer = await ledger.saveCustomer({
    name: 'தமிழ், "பிரியா"\nPollachi',
    phone: "123",
    city: "Pollachi",
  });
  const settings = await ledger.settings();
  await ledger.saveSettings({ ...settings, round_rupee: true });
  for (let i = 0; i < 35; i++)
    await ledger.checkout(
      order({
        discount_paise: 51,
        method: i % 2 ? "upi" : "cash",
        customer_id: customer.id,
      }),
    );
  await ledger.adjust({
    sale_id: prior.id,
    operation_id: "prior-month-refund",
    kind: "refund",
    amount_paise: 500,
    reason: "Previous month refund — தமிழ்",
  });
  const content = await createBackup(ledger, new MemoryImages());
  await db.close();
  const backup = resolve(artifacts, "monthly-backup.json");
  writeFileSync(backup, content);
  await ready(page);
  await page.locator('[data-nav="settings"]').click();
  await page.locator("#restore-file").setInputFiles(backup);
  await expect(page.locator("#restore-dialog")).toBeVisible();
  await page.locator("#restore-confirm").fill("RESTORE");
  await page.locator("#restore-button").click();
  await expect(page.locator("#storage-status")).toContainText("SQLite");
  await page.locator('[data-nav="sales"]').click();
  await page.locator('#sales-filter [data-preset="month"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(10);
  await expect(page.locator("#sales-pagination")).toContainText("of 35 bills");
  await page.locator('[data-nav="reports"]').click();
  await expect(page.locator("#report-totals")).toContainText(
    "₹5,910.00".replace(",", ""),
  );
  const wait = page.waitForEvent("download");
  await page.locator('[data-export="pdf"]').click();
  const download = await wait;
  await download.saveAs(resolve(artifacts, "monthly-auditor.pdf"));
  const csvWait = page.waitForEvent("download");
  await page.locator('[data-export="csv"]').click();
  await (await csvWait).saveAs(resolve(artifacts, "monthly-auditor.csv"));
});
