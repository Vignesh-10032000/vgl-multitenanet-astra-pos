import { expect, test } from "@playwright/test";

test("supplied feature and contact sections work in English and Tamil", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator("#features")).toBeVisible();
  await expect(page.locator("#contact")).toContainText("vigneshgrowthlab@gmail.com");
  await expect(page.locator('a[href="https://wa.me/918220034139"]')).toBeVisible();
  await expect(page.locator("#signin #form")).toBeVisible();

  await page.locator("#lang").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ta");
  await expect(page.locator("#signin .divider")).toContainText("கடை குழு உள்நுழைவு");
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});
