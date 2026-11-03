import { test, expect } from "@playwright/test";
import { unlockInclusiveFixture as unlockFixture } from "./access-helper.js";
import { mkdirSync } from "node:fs";

test("top-bar language and theme survive offline reload without changing the bill", async ({ page, context }) => {
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await unlockFixture(page);
  await expect(page.locator(".product-tile")).toHaveCount(36);
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator('[data-quantity-action="increment"]').click();
  await expect(page.locator("#total-net")).toHaveText("₹340.00");
  const name = await page.locator('.product-tile').first().textContent();
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("#theme-toggle")).toHaveAttribute("aria-pressed", "true");
  await page.locator("#locale-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ta");
  await expect(page.locator("#locale-label")).toHaveText("English");
  await expect(page.locator('[data-nav="customers"]')).toContainText("வாடிக்கையாளர்கள்");
  await expect(page.locator("#pay-button")).not.toContainText("Pay now");
  await expect(page.locator("#total-net")).toHaveText("₹340.00");
  await expect(page.locator('.product-tile').first()).toHaveText(name);
  await page.locator("#pay-button").click();
  await expect(page.locator("#payment-method option[value='CASH']")).toHaveText("ரொக்கம்");
  await expect(page.locator("#payment-dialog")).toBeVisible();
  await page.locator('#payment-dialog [data-dialog-close]').first().click();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("html")).toHaveAttribute("lang", "ta");
  await expect(page.locator("#total-net")).toHaveText("₹340.00");
  // Keep the local origin available to reload its bundled assets; reject all external requests.
  await context.route(/https?:\/\/(?!127\.0\.0\.1:5175)/, route => route.abort());
  await page.locator('[data-nav="customers"]').click();
  await page.locator("#add-customer").click();
  await page.locator("#customer-name").fill("தமிழ் பெயர்");
  await page.locator("#customer-city").fill("சென்னை");
  await page.locator("#customer-dialog button[type='button'][data-close]").last().click();
  await page.locator('[data-nav="products"]').click();
  await page.locator("#add-product").click();
  await expect(page.locator('#product-form [name="name"]')).toBeVisible();
  await expect(page.locator('#product-form')).not.toContainText('restaurant.');
  await page.locator('#product-dialog button[data-close]').first().click();
  for (const route of ["sales", "reports", "dashboard", "settings", "billing"]) {
    await page.locator(`[data-nav="${route}"]`).click();
    await expect(page.locator("#theme-toggle")).toBeVisible();
    expect(await page.locator("body").evaluate(el => getComputedStyle(el).backgroundColor)).toBe("rgb(10, 20, 37)");
  }
  mkdirSync("test-results/preferences", { recursive: true });
  await page.screenshot({ path: "test-results/preferences/billing-dark-tamil.png" });
  await page.locator("#locale-toggle").click();
  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.locator("#total-net")).toHaveText("₹340.00");
  await page.screenshot({ path: "test-results/preferences/billing-light-english.png" });
  expect(errors).toEqual([]);
});

for (const viewport of [{ width: 1024, height: 768 }, { width: 1070, height: 716 }, { width: 732, height: 336 }, { width: 390, height: 844 }]) {
  test(`top-bar controls remain tappable in both languages at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await unlockFixture(page);
    await expect(page.locator(".product-tile")).toHaveCount(36);
    for (const language of ["en", "ta"]) {
      if (language === "ta") await page.locator("#locale-toggle").click();
      for (const selector of ["#locale-toggle", "#theme-toggle", "#lock-workspace", "#last-receipt"]) {
        const bounds = await page.locator(selector).boundingBox();
        expect(bounds.width).toBeGreaterThanOrEqual(44);
        expect(bounds.height).toBeGreaterThanOrEqual(44);
        expect(bounds.x).toBeGreaterThanOrEqual(0);
        expect(bounds.x + bounds.width).toBeLessThanOrEqual(viewport.width);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width);
    }
  });
}
