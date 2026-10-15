import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("login preview is complete, accessible and fills the desktop layout", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/login");
  await expect(page.getByText("Illustrative sample data")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Build repeat business" })).toBeVisible();
  await expect(page.locator(".sample-bill-total")).toContainText("₹519.75");
  await expect(page.locator(".sample-product")).toHaveCount(3);
  for (const width of [1920, 1440, 1100]) {
    await page.setViewportSize({ width, height: 1080 });
    const form = await page.locator(".login-panel").boundingBox();
    const visual = await page.locator(".login-visual").boundingBox();
    expect(Math.abs(form.x + form.width - visual.x)).toBeLessThan(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1080 });
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({ path: "test-results/login-desktop.png", fullPage: true });
});

test("mobile sign-in fields fill the form without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Explore the demo" })).toBeVisible();
  const username = await page.locator('[name="username"]').boundingBox();
  const form = await page.locator("#login-form").boundingBox();
  expect(Math.abs(username.width - form.width)).toBeLessThan(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/login-mobile.png", fullPage: true });
});

for (const status of [500, 503]) {
  test(`demo outage ${status} shows a helpful message and support reference`, async ({ page }) => {
    await page.goto("/login");
    await page.route("**/api/v1/auth/demo-login", (route) => route.fulfill({
      status,
      contentType: "application/problem+json",
      body: JSON.stringify({ detail: "An unexpected error occurred.", request_id: "demo-support-123" }),
    }));
    await page.getByRole("button", { name: "Explore the demo" }).click();
    await expect(page.locator("#demo-error")).toContainText("The demo is temporarily unavailable");
    await expect(page.locator("#demo-error")).toContainText("Support reference: demo-support-123");
    await expect(page.locator("#login-error")).toBeEmpty();
    await expect(page.getByRole("button", { name: "Explore the demo" })).toBeEnabled();
    await expect(page.locator('#login-form button[type="submit"]')).toBeEnabled();
  });
}

test("demo network failure allows retry", async ({ page }) => {
  await page.goto("/login");
  await page.route("**/api/v1/auth/demo-login", (route) => route.abort("failed"));
  await page.getByRole("button", { name: "Explore the demo" }).click();
  await expect(page.locator("#demo-error")).toContainText("Check your internet connection");
  await expect(page.getByRole("button", { name: "Explore the demo" })).toBeEnabled();
});

test("branded demo login opens a populated workspace", async ({ page }) => {
  await page.goto("/login");

  await expect(page.getByRole("img", { name: "Vignesh Growth Lab" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Welcome to smarter retail" })).toBeVisible();

  await Promise.all([
    page.waitForURL("**/pos"),
    page.getByRole("button", { name: "Explore the demo" }).click(),
  ]);

  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator("#pos-product-grid").locator("button")).toHaveCount(8);

  await page.goto("/");
  await expect(page.locator('[data-metric="bills"] .metric-value')).not.toHaveText("—");
  await expect(page.locator("#recent-sales tr")).toHaveCount(4);
});
