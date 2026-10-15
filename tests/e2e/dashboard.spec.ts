import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test.beforeEach(async ({ page, request }) => {
  const login = await request.post("/api/v1/auth/demo-login", {
    data: {}, headers: { "Idempotency-Key": randomUUID() },
  });
  expect(login.ok()).toBeTruthy();
  const session = await login.json();
  await page.addInitScript((value) => {
    sessionStorage.setItem("vglpos.session", JSON.stringify(value));
  }, session);
});

async function waitForOverview(page) {
  await expect(page.locator("#dashboard-content")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator('[data-metric="net"] .metric-value')).toHaveText("₹1,391.28");
}

test("detailed dashboard carries forward stock, customer, tax and transaction features", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");
  await waitForOverview(page);
  await expect(page.locator('[data-metric="week"] .metric-value')).toHaveText("₹4,354.85");
  await expect(page.locator('[data-metric="tax"] .metric-value')).toHaveText("₹132.28");
  await expect(page.locator('[data-metric="average"] .metric-value')).toHaveText("₹347.82");
  await expect(page.locator(".dashboard-ranked-item")).toHaveCount(5);
  await expect(page.locator(".dashboard-stock-item")).toHaveCount(3);
  await expect(page.locator(".dashboard-payment-item")).toHaveCount(3);
  await expect(page.locator("#recent-sales tr")).toHaveCount(8);
  await expect(page.locator("#recent-sales")).toContainText("Ananya Raman");
  await expect(page.locator("#recent-sales a").first()).toHaveAttribute("href", /\/receipt\/\d+/);
  expect(errors).toEqual([]);
  await page.setViewportSize({ width: 1600, height: 1100 });
  await page.screenshot({ path: "test-results/dashboard-desktop.png", fullPage: true });
});

test("dashboard is accessible in both themes and fits mobile", async ({ page }) => {
  await page.goto("/");
  await waitForOverview(page);
  for (const theme of ["light", "dark"]) {
    await page.evaluate((value) => {
      document.documentElement.dataset.theme = value;
    }, theme);
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(result.violations, theme).toEqual([]);
  }
  await page.screenshot({ path: "test-results/dashboard-dark.png", fullPage: true });
  await page.evaluate(() => { document.documentElement.dataset.theme = "light"; });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect(page.getByRole("button", { name: "Refresh", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/dashboard-mobile.png", fullPage: true });
});

test("historical date has empty sales without erasing current stock counts", async ({ page }) => {
  await page.goto("/");
  await waitForOverview(page);
  await page.locator("#dashboard-date").fill("2000-01-01");
  await expect(page.locator('[data-metric="net"] .metric-value')).toHaveText("₹0.00");
  await expect(page.locator('[data-metric="products"] .metric-value')).toHaveText("8");
  await expect(page.locator("#top-products")).toContainText("No completed product sales");
  await expect(page.locator(".bar-column")).toHaveCount(7);
});

test("Tamil dashboard translates headings and product names", async ({ page }) => {
  await page.goto("/");
  await waitForOverview(page);
  await page.getByRole("button", { name: "Switch language" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ta");
  await expect(page.locator("#dashboard-heading")).toHaveText("உங்கள் வணிகத்தின் தெளிவான பார்வை.");
  await expect(page.locator("#top-products")).toContainText("பொன்னி அரிசி");
  await expect(page.locator("#low-stock")).toContainText("ஃபில்டர் காபி");
});

test("failed refresh retains last confirmed data and permits retry", async ({ page }) => {
  await page.goto("/");
  await waitForOverview(page);
  await page.route("**/api/v1/reports/dashboard?*", (route) => route.fulfill({
    status: 503, contentType: "application/problem+json", body: JSON.stringify({ detail: "Unavailable" }),
  }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.locator("#dashboard-error")).toContainText("last successful update");
  await expect(page.locator('[data-metric="net"] .metric-value')).toHaveText("₹1,391.28");
  await expect(page.getByRole("button", { name: "Refresh", exact: true })).toBeEnabled();
  await page.unroute("**/api/v1/reports/dashboard?*");
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(page.locator("#dashboard-error")).toBeHidden();
  await waitForOverview(page);
});

test("initial outage ends skeletons and supports recovery", async ({ page }) => {
  await page.route("**/api/v1/reports/dashboard?*", (route) => route.fulfill({
    status: 503, contentType: "application/problem+json", body: JSON.stringify({ detail: "Unavailable" }),
  }));
  await page.goto("/");
  await expect(page.locator("#dashboard-content")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator("#dashboard-error")).toBeVisible();
  await expect(page.locator(".skeleton-line")).toHaveCount(0);
  await page.unroute("**/api/v1/reports/dashboard?*");
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await waitForOverview(page);
});
