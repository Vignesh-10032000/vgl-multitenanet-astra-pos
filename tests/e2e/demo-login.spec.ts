import { expect, test } from "@playwright/test";

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
