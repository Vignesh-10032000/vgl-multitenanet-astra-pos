import { test, expect } from "@playwright/test";
import { unlockInclusiveFixture as unlockFixture } from "./access-helper.js";

async function ready(page) {
  await page.goto("/");
  await unlockFixture(page);
  await expect(page.locator(".product-tile")).toHaveCount(36);
}

test("BILL-UNDO-01 an undo from a completed bill cannot restore sold items", async ({
  page,
}) => {
  await ready(page);
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator('[data-product-id="menu-002"]').click();
  await page.locator('[data-remove-product-id="menu-001"]').click();
  await page.locator("#pay-button").click();
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-dialog")).toBeVisible();
  await page.locator("#receipt-dialog [data-close]").click();
  await page.locator(".toast").getByRole("button", { name: "Undo" }).click();
  await expect(page.locator("#cart-count")).toHaveText("0");
  await expect(page.locator("#total-net")).toHaveText("₹0.00");
});

test("BILL-PHOTO-01 local photographs occupy the intended tap tile without clipping", async ({
  page,
}) => {
  await ready(page);
  const tile = page.locator(".product-tile").first();
  expect((await tile.boundingBox()).height).toBeGreaterThanOrEqual(210);
  expect(
    (await tile.locator(".product-visual").boundingBox()).width,
  ).toBeGreaterThan(90);
  expect((await tile.locator(".product-visual").boundingBox()).height).toBe(96);
});

test("BILL-UNDO-02 undo merges with a reselected portion instead of creating duplicate lines", async ({ page }) => {
  await ready(page);
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator('[data-remove-product-id="menu-001"]').click();
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator(".toast").getByRole("button", { name: "Undo" }).click();
  await expect(page.locator("#cart-count")).toHaveText("1");
  await expect(page.locator('[data-quantity-input="menu-001"]')).toHaveValue("2.000");
  await expect(page.locator("#total-net")).toHaveText("₹340.00");
  await page.locator("#pay-button").click();
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-dialog")).toBeVisible();
});

test("original quantity controls, undo and discount retain string menu identifiers", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await ready(page);
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator('[data-quantity-action="increment"]').click();
  await expect(page.locator("#total-net")).toHaveText("₹340.00");
  await page.locator('[data-quantity-input="menu-001"]').fill("3");
  await page.locator('[data-quantity-input="menu-001"]').press("Tab");
  await expect(page.locator("#total-net")).toHaveText("₹510.00");
  await page.locator("#order-discount").fill("10.00");
  await expect(page.locator("#total-net")).toHaveText("₹500.00");
  await page.locator('[data-remove-product-id="menu-001"]').click();
  await page.locator(".toast").getByRole("button", { name: "Undo" }).click();
  await expect(page.locator("#total-net")).toHaveText("₹500.00");
  await page.locator("#pay-button").click();
  await page.locator('[data-cash="2000"]').click();
  await expect(page.locator("#payment-change")).toHaveText("₹1,500.00");
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-preview")).toContainText("₹500.00");
  expect(errors).toEqual([]);
});

test("touch hold/recall survive reload without desktop quick keys or a shift", async ({
  page,
}) => {
  await ready(page);
  await expect(page.locator("#configure-quick-keys")).toHaveCount(0);
  await expect(page.locator(".shortcut-strip")).toHaveCount(0);
  await page.locator('[data-product-id="menu-001"]').click();
  await expect(page.locator("#total-net")).toHaveText("₹170.00");
  await page.locator("#hold-bill").click();
  await page.locator('#hold-form [name="label"]').fill("Table 4");
  await page
    .locator("#hold-form")
    .getByRole("button", { name: "Hold", exact: true })
    .click();
  await expect(page.locator("#cart-count")).toHaveText("0");
  await page.reload();

  await page.locator("#recall-bill").click();
  await expect(page.locator("#held-list")).toContainText("Table 4");
  await page.locator("[data-recall-hold]").click();
  await expect(page.locator("#total-net")).toHaveText("₹170.00");
  await page.reload();
  await expect(page.locator("#total-net")).toHaveText("₹170.00");
  await page.locator("#pay-button").click();
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-preview")).toContainText("000001");
});

test("repeated complete taps and failed print/reprint retain one saved bill and next final number", async ({
  page,
}) => {
  await ready(page);
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator("#pay-button").click();
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.locator("#complete-sale").evaluate((button) => {
    button.click();
    button.click();
    button.click();
  });
  await expect(page.locator("#receipt-preview")).toContainText("000001");
  await page.evaluate(() => {
    window.print = () => {
      throw new Error("Simulated unavailable printer");
    };
  });
  await page.locator("#print-receipt").click();
  await expect(page.locator("#print-status")).toContainText(
    "Bill remains saved. Printing failed",
  );
  await page.locator("#receipt-dialog [data-close]").click();
  await page.reload();
  await page.locator("#last-receipt").click();
  await expect(page.locator("#receipt-preview")).toContainText("000001");
  await page.locator("#receipt-dialog [data-close]").click();
  await page.locator('[data-nav="sales"]').click();
  await expect(page.locator("#sales-list tbody tr")).toHaveCount(1);
  await expect(page.locator("#sales-totals")).toContainText("₹170.00");
  await page.locator('[data-nav="billing"]').click();
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator("#pay-button").click();
  await page.locator("#complete-sale").click();
  await expect(page.locator("#receipt-preview")).toContainText("000002");
});
