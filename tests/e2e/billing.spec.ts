import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

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

async function scan(page, barcode: string) {
  await page.evaluate((value) => {
    for (const key of value) {
      document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  }, barcode);
}

test("scanner billing restores the cart, accepts split tender, and prints every paper size", async ({ page }, testInfo) => {
  await signIn(page);

  const search = page.locator("#pos-search");
  await search.fill("keep this text");
  await scan(page, "8901234567890");
  await expect(search).toHaveValue("keep this text");
  await expect(page.locator('[data-quantity-input="1"]')).toHaveValue("1.000");
  await expect(page.locator("#total-net")).toHaveText("₹118.00");

  await scan(page, "8901234567890");
  await expect(page.locator('[data-quantity-input="1"]')).toHaveValue("2.000");
  await expect(page.locator("#total-net")).toHaveText("₹236.00");

  await page.reload();
  await expect(page.locator('[data-quantity-input="1"]')).toHaveValue("2.000");
  await expect(page.locator("#total-net")).toHaveText("₹236.00");

  await page.keyboard.press("F1");
  await expect(page.locator("#help-dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.keyboard.press("F2");
  await expect(page.locator("#payment-dialog")).toBeVisible();

  await page.locator('[data-cash="200"]').click();
  await page.locator("#add-payment-row").click();
  const rows = page.locator(".payment-row");
  await expect(rows).toHaveCount(2);
  await rows.nth(1).locator("select").selectOption("UPI");
  await rows.nth(1).locator('input[inputmode="decimal"]').fill("36.00");
  await rows.nth(1).locator('input:not([inputmode="decimal"])').fill("UPI-E2E-001");
  await expect(page.locator("#payment-balance")).toHaveText("₹0.00");
  await expect(page.locator("#payment-change")).toHaveText("₹0.00");
  await expect(page.locator("#complete-sale")).toBeEnabled();

  await Promise.all([
    page.waitForURL(/\/receipt\/\d+/),
    page.locator("#complete-sale").click(),
  ]);
  await expect(page.locator("#invoice")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator("#receipt-total")).toHaveText("₹236.00");
  await expect(page.locator("#receipt-number")).toContainText("WEB/");

  for (const paper of ["58", "80", "a5"]) {
    await page.emulateMedia({ media: "screen" });
    await page.locator(`[data-paper-value="${paper}"]`).click();
    await page.emulateMedia({ media: "print" });
    const options = paper === "a5"
      ? { format: "A5" as const }
      : { width: `${paper}mm`, height: "220mm" };
    await page.pdf({ path: testInfo.outputPath(`receipt-${paper}.pdf`), ...options });
  }
});

test("POS has no automatic WCAG 2.2 AA violations in either theme", async ({ page }) => {
  await signIn(page);

  for (const theme of ["light", "dark"]) {
    await page.evaluate((value) => {
      localStorage.setItem("vglpos.theme", value);
      document.documentElement.dataset.theme = value;
    }, theme);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    expect(results.violations, `${theme} theme accessibility violations`).toEqual([]);
  }
});

test("POS first contentful paint stays below the 3G budget", async ({ page }) => {
  await signIn(page);
  const session = await page.context().newCDPSession(page);
  await session.send("Network.enable");
  await session.send("Network.setCacheDisabled", { cacheDisabled: true });
  await session.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 150,
    downloadThroughput: (1_638_400 / 8),
    uploadThroughput: (750_000 / 8),
    connectionType: "cellular3g",
  });

  await page.reload();
  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
  const firstContentfulPaint = await page.evaluate(() =>
    performance.getEntriesByName("first-contentful-paint")[0]?.startTime,
  );

  expect(firstContentfulPaint).toBeDefined();
  expect(firstContentfulPaint).toBeLessThan(1_500);
});
