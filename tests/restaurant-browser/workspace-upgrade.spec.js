import { test, expect } from "@playwright/test";
import { setup, order, MemoryImages } from "../restaurant/helpers.js";
import { createBackup } from "../../restaurant/backup.js";
import { unlockInclusiveFixture as unlockFixture } from "./access-helper.js";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
const output = resolve("test-results/workspace-upgrade");
mkdirSync(output, { recursive: true });

async function seed(page) {
  await page.clock.setFixedTime(new Date("2026-10-30T04:00:00.000Z"));
  let now = "2026-10-12T04:00:00.000Z";
  const { ledger, db } = await setup({ now: () => now });
  let source, weekly, monthly;
  try {
    await ledger.checkout(order());
    now = "2026-10-29T04:00:00.000Z";
    await ledger.checkout(order({ method: "upi" }));
    now = "2026-10-30T04:00:00.000Z";
    const products = (await ledger.products()).slice(0, 7);
    for (let i = 0; i < 23; i++) {
      const p = products[i % products.length];
      await ledger.checkout(
        order({
          items: [
            {
              product_id: p.id,
              name: p.name,
              portion: p.portion,
              unit_paise: p.price_paise,
              quantity: 1,
            },
          ],
          method: i % 2 ? "cash" : "upi",
          tendered_paise: p.price_paise,
        }),
      );
    }
    weekly = (await ledger.report({ from: "2026-10-26", to: "2026-10-30" }))
      .totals.net_paise;
    monthly = (await ledger.report({ from: "2026-10-01", to: "2026-10-30" }))
      .totals.net_paise;
    source = await createBackup(ledger, new MemoryImages());
  } finally {
    await db.close();
  }
  await page.goto("/");
  await unlockFixture(page);
  await page.locator('[data-nav="settings"]').click();
  await page
    .locator("#restore-file")
    .setInputFiles({
      name: "workspace-fixture.json",
      mimeType: "application/json",
      buffer: Buffer.from(source),
    });
  await expect(page.locator("#restore-dialog")).toBeVisible();
  await page.locator("#restore-confirm").fill("RESTORE");
  await page.locator("#restore-button").click();
  await expect(page.locator("#storage-status")).toContainText("SQLite");
  return { weekly, monthly };
}

test("PHONE-NAV-01 short landscape keeps every navigation link reachable without changing the draft", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 383 });
  await page.goto('/');
  await unlockFixture(page);
  await page.locator('[data-product-id="menu-001"]').click();
  await expect(page.locator('#total-net')).toHaveText('₹170.00');
  const draft = await page.locator('.cart-line').allTextContents();
  for (const native of ['false', 'true']) {
    await page.evaluate(value => document.body.dataset.native = value, native);
    for (const screen of ['dashboard', 'products', 'customers', 'sales', 'reports', 'settings', 'billing']) {
      await page.locator(`[data-nav="${screen}"]`).click({ timeout: 5000 });
      await expect(page.locator(`[data-view="${screen}"]`)).toBeVisible();
    }
  }
  expect(await page.locator('.cart-line').allTextContents()).toEqual(draft);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(900);
});

test("PHONE-NAV-02 compact landscape keeps navigation labels and branding inside the sidebar", async ({page}) => {
  await page.setViewportSize({width:732,height:336});
  await page.goto('/');
  await unlockFixture(page);
  for (const screen of ['dashboard','products','customers','sales','reports','settings','billing']) {
    const link=page.locator(`[data-nav="${screen}"]`);
    await link.click();
    await expect(page.locator(`[data-view="${screen}"]`)).toBeVisible();
    const sizes=await link.evaluate(element=>{
      const link=element.getBoundingClientRect(), label=element.querySelector('span').getBoundingClientRect();
      const sidebar=element.closest('aside').getBoundingClientRect();
      return {left:label.left-link.left,right:link.right-label.right,sidebarRight:sidebar.right-link.right,width:link.width,height:link.height};
    });
    expect(sizes.left).toBeGreaterThanOrEqual(0);
    expect(sizes.right).toBeGreaterThanOrEqual(0);
    expect(sizes.sidebarRight).toBeGreaterThanOrEqual(-1);
    expect(sizes.width).toBeGreaterThanOrEqual(44);
    expect(sizes.height).toBeGreaterThanOrEqual(44);
  }
  const logo=await page.locator('#nav-logo').boundingBox();
  const sidebar=await page.locator('.side-nav').boundingBox();
  expect(logo.width).toBeLessThanOrEqual(sidebar.width);
});

test("LOGIN-UI-01 first owner setup, wrong password, lock, session reload and phone layout", async ({
  page,
}) => {
  await page.goto("/#sales");
  await expect(page.locator("#access-form")).toBeVisible();
  await expect(page.locator(".app-shell")).not.toBeVisible();
  await expect(page.locator("#access-username")).toHaveValue("");
  await page.screenshot({
    path: resolve(output, "login-desktop.png"),
    fullPage: true,
  });
  await page.locator("#access-username").fill("owner");
  await page.locator("#access-password").fill("short");
  await page.locator("#access-confirm").fill("short");
  await page.locator("#access-submit").click();
  await expect(page.locator("#access-error")).toContainText("10–128");
  await page.locator("#access-password").fill("A-test-only-password!");
  await page.locator("#access-confirm").fill("A-test-only-password!");
  await page.locator("#access-submit").click();
  await expect(page.locator("#access-screen")).not.toBeVisible();
  await expect(page.locator('[data-view="sales"]')).toBeVisible();
  await page.locator("#lock-workspace").click();
  await expect(page.locator("#access-confirm-row")).not.toBeVisible();
  await page.locator("#access-password").fill("Wrong-password!");
  await page.locator("#access-submit").click();
  await expect(page.locator("#access-error")).toContainText("incorrect");
  await expect(page.locator(".app-shell")).not.toBeVisible();
  await page.setViewportSize({ width: 412, height: 915 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(412);
  await page.screenshot({
    path: resolve(output, "login-phone.png"),
    fullPage: true,
  });
  await page.locator("#access-password").fill("A-test-only-password!");
  await page.locator("#access-submit").click();
  await expect(page.locator("#access-screen")).not.toBeVisible();
  await page.reload();
  await expect(page.locator("#access-screen")).not.toBeVisible();
});

test("WORKSPACE-UI-01 reference Sales layout, paging and analytics retain live ledger features", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const { weekly, monthly } = await seed(page);
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(10);
  await expect(page.locator("#sales-pagination")).toContainText("of 23 bills");
  await page.getByRole("button", { name: "Next page", exact: true }).click();
  await expect(page.locator("#sales-list tbody tr").first()).toContainText(
    "000015",
  );
  await expect(page.locator("#sales-pagination")).toContainText("Page 2 of 3");
  await page.locator("[data-view-sale]").first().click();
  await expect(page.locator("#receipt-preview")).toContainText("000015");
  await page.locator("#receipt-dialog [data-close]").click();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: resolve(output, "sales-desktop.png") });
  await page.locator('[data-nav="reports"]').click();
  await expect(page.locator("#analytics-cards .analytics-stat")).toHaveCount(4);
  await expect(page.locator("#revenue-chart svg")).toBeVisible();
  await expect(page.locator(".payment-donut svg")).toBeVisible();
  expect(
    (await page.locator(".payment-donut svg").boundingBox()).height,
  ).toBeGreaterThanOrEqual(180);
  await expect(page.locator("#analytics-top-items tbody tr")).toHaveCount(5);
  await expect(page.locator("[data-export]:visible")).toHaveCount(3);
  await page.locator("#trend-grouping").selectOption("weekly");
  await page.locator('[data-report-tab="items"]').click();
  await expect(page.locator("#report-details")).toContainText(
    "Selected payment",
  );
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: resolve(output, "reports-desktop.png") });
  await page.locator('[data-nav="dashboard"]').click();
  const values = page.locator(".period-revenue-card strong");
  await expect(values).toHaveCount(2);
  const fmt = (paise) =>
    `₹${Math.trunc(paise / 100)}.${String(paise % 100).padStart(2, "0")}`;
  await expect(values.nth(0)).toHaveText(fmt(weekly));
  await expect(values.nth(1)).toHaveText(fmt(monthly));
  await page.screenshot({
    path: resolve(output, "dashboard-revenue.png"),
    fullPage: true,
  });
  for (const width of [1280, 1024, 412]) {
    await page.setViewportSize({ width, height: 900 });
    for (const screen of ["sales", "reports", "products"]) {
      await page.locator(`[data-nav="${screen}"]`).click();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth),
        `${screen} overflow at ${width}`,
      ).toBeLessThanOrEqual(width);
    }
  }
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.locator("#add-product").click();
  const fields = await page
    .locator("#product-form label:not(.check) input")
    .evaluateAll((inputs) =>
      inputs.map((input) => ({
        width: input.getBoundingClientRect().width,
        height: input.getBoundingClientRect().height,
      })),
    );
  expect(fields.every((field) => field.height >= 44 && field.width > 150)).toBe(
    true,
  );
  await page.screenshot({ path: resolve(output, "product-form.png") });
  expect(errors).toEqual([]);
});
