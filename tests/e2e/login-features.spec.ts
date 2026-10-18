import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("LOGIN-04 implemented feature benefits and contact CTA remain usable in both languages", async ({ page }) => {
  const failures: string[] = [];
  page.on("pageerror", (error) => failures.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 500) failures.push(`${response.status()} ${new URL(response.url()).pathname}`);
  });
  await page.goto("/login");
  await expect(page.locator(".login-feature-card")).toHaveCount(6);
  await expect(page.locator(".login-access-proof")).toContainText("authenticator MFA");
  await expect(page.locator(".login-feature-section")).toContainText("GSTR-1 JSON exports");
  await expect(page.locator(".login-feature-section")).toContainText("58 mm, 80 mm or A5");
  await expect(page.locator(".login-feature-section")).toContainText("outstanding balances");
  for (const locale of ["en", "ta"]) {
    if (locale === "ta") {
      await page.locator("#login-locale").click();
      await expect(page.locator("html")).toHaveAttribute("lang", "ta");
    }
    for (const width of [1920, 1440, 1100, 1024, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 900 });
      await expect(page.locator("#login-features-title")).toBeVisible();
      await expect(page.locator(".login-feature-card").last()).toBeVisible();
      await expect(page.locator("i[data-lucide]:visible")).toHaveCount(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const overflow = await page.locator(".login-feature-card").evaluateAll((cards) => cards.some(
        (card) => card.scrollWidth > card.clientWidth + 1,
      ));
      expect(overflow, `${locale} at ${width}px`).toBe(false);
    }
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
    await page.evaluate(() => (document.activeElement as HTMLElement)?.blur());
    await page.screenshot({ path: `test-results/login-features-mobile-${locale}.png`, fullPage: true });
  }
  await page.locator("#login-locale").click();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator(".login-tailored-link").click();
  await expect(page.locator("#login-contact-title")).toBeInViewport();
  await page.evaluate(() => { (document.activeElement as HTMLElement)?.blur(); window.scrollTo(0, 0); });
  await page.screenshot({ path: "test-results/login-features-desktop.png", fullPage: true });
  expect(failures).toEqual([]);
});
