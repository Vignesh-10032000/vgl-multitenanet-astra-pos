import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

const imageDir = resolve("docs/images");

async function signIn(page) {
  await page.goto("/login");
  await page.locator('[name="company_code"]').fill("E2E");
  await page.locator('[name="username"]').fill("cashier");
  await page.locator('[name="password"]').fill("Browser-test-password-42!");
  await page.locator('[name="branch_id"]').fill("1");
  await page.locator('[name="terminal_id"]').fill("1");
  await Promise.all([
    page.waitForURL("**/pos"),
    page.locator("#login-form").getByRole("button", { name: /sign in/i }).click(),
  ]);
  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
  await page.waitForFunction(() => (
    document.querySelector("#shift-status")?.getAttribute("data-state") === "open"
      || document.querySelector("#shift-open-dialog")?.open
  ));
  if (await page.locator("#shift-open-dialog").isVisible()) {
    await page.locator('#shift-open-form [data-denomination="100"]').fill("1");
    await page.locator("#shift-open-form").getByRole("button", { name: /open shift/i }).click();
    await expect(page.locator("#shift-open-dialog")).toBeHidden();
  }
}

test("capture synthetic-data user-guide screens", async ({ page }) => {
  mkdirSync(imageDir, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/login");
  await page.screenshot({ path: resolve(imageDir, "login-en.png"), fullPage: true });

  await signIn(page);
  await page.screenshot({ path: resolve(imageDir, "pos-en.png"), fullPage: true });

  await page.goto("/");
  await expect(page.locator("main")).toBeVisible();
  await page.screenshot({ path: resolve(imageDir, "dashboard-en.png"), fullPage: true });

  await page.goto("/reports");
  await expect(page.locator("main")).toBeVisible();
  await page.screenshot({ path: resolve(imageDir, "reports-en.png"), fullPage: true });

  await page.goto("/compliance");
  await expect(page.locator("main")).toBeVisible();
  await page.screenshot({ path: resolve(imageDir, "compliance-en.png"), fullPage: true });
});
