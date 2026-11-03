import { test, expect } from "@playwright/test";
import { unlockInclusiveFixture as unlockFixture } from "./access-helper.js";
import { mkdirSync, writeFileSync } from "node:fs";
const artifacts = "test-results/payment-qr";
mkdirSync(artifacts, { recursive: true });
async function ready(page) {
  await page.goto("/");
  await unlockFixture(page);
  await expect(page.locator(".product-tile")).toHaveCount(36);
}
async function captureQr(page, name) {
  const image = page.locator("#payment-qr-dialog img");
  await expect(image).toBeVisible();
  await expect(image).toHaveAttribute("src", /^data:image\/png;base64,/);
  const data = (await image.getAttribute("src")).split(",")[1];
  writeFileSync(`${artifacts}/${name}.png`, Buffer.from(data, "base64"));
}
test("UPI-QR-UI-01 demo full/split preview is non-payment, preserves draft and writes no sale", async ({
  page,
}) => {
  const errors = [],
    external = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("request", (r) => {
    if (
      !r.url().startsWith("http://127.0.0.1:5175") &&
      !r.url().startsWith("data:")
    )
      external.push(r.url());
  });
  await ready(page);
  await page.locator('[data-product-id="menu-001"]').click();
  await expect(page.locator("#total-net")).toHaveText("₹170.00");
  await page.locator("#pay-button").click();
  await expect(page.locator("#show-payment-qr")).toBeHidden();
  await page.locator("#payment-method").selectOption("UPI");
  await page.locator("#show-payment-qr").click();
  await expect(page.locator("[data-qr-mode]")).toHaveText("DEMO · NO PAYMENT");
  await expect(page.locator("[data-qr-amount]")).toHaveText("₹170.00");
  await expect(page.locator("[data-qr-hint]")).toContainText(
    "cannot receive money",
  );
  await captureQr(page, "demo-full");
  await page.locator("#payment-qr-dialog [data-qr-copy=back]").click();
  await expect(page.locator("#show-payment-qr")).toBeFocused();
  await expect(page.locator("#payment-dialog")).toBeVisible();
  await page.locator("#split-payment").click();
  await page.locator("#cash-tender").fill("50.00");
  await page.locator("#upi-received").fill("120.00");
  await page.locator("#show-payment-qr").click();
  await expect(page.locator("[data-qr-amount]")).toHaveText("₹120.00");
  await captureQr(page, "demo-split");
  await page
    .locator("#payment-qr-dialog")
    .screenshot({ path: `${artifacts}/demo-desktop.png` });
  // A late payment edit must remove the displayed QR immediately.
  await page.locator("#upi-received").evaluate((input) => {
    input.value = "119.00";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(page.locator("[data-qr-status]")).toContainText(
    "amount changed",
  );
  await expect(page.locator("#payment-qr-dialog img")).toBeHidden();
  await page.keyboard.press("Escape");
  await page.locator("#upi-received").fill("171");
  await page.locator("#show-payment-qr").click();
  await expect(page.locator("[data-qr-status]")).toContainText("GPay share");
  await expect(page.locator("#payment-qr-dialog img")).toBeHidden();
  await expect(page.locator("[data-qr-details]")).toBeHidden();
  await page.keyboard.press("Escape");
  await page.locator("#payment-dialog [data-dialog-close]").first().click();
  await expect(page.locator(".cart-line")).toHaveCount(1);
  await page.locator("[data-nav=sales]").click();
  await expect(page.locator("#sales-list [data-view-sale]")).toHaveCount(0);
  await page.locator("[data-nav=settings]").click();
  await expect(page.locator("[name=upi_id]")).toHaveValue("");
  await expect(page.locator("[name=upi_confirmed]")).not.toBeChecked();
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});
test("UPI-QR-UI-02 verified fixture uses merchant QR, Cash hides it and short landscape fits", async ({
  page,
}) => {
  await ready(page);
  await page.locator("[data-nav=settings]").click();
  await page.locator("[name=upi_id]").fill("fixture@example");
  await page.locator("[name=upi_payee]").fill("Fixture & Restaurant");
  await page.locator("[name=upi_confirmed]").check();
  await page.locator("#settings-form .button-primary").click();
  await page.locator("[data-nav=billing]").click();
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator("#pay-button").click();
  await page.locator("#payment-method").selectOption("UPI");
  await page.locator("#show-payment-qr").click();
  await expect(page.locator("[data-qr-mode]")).toHaveText("GPay / UPI");
  await expect(page.locator("[data-qr-upi]")).toHaveText("fixture@example");
  await captureQr(page, "merchant-fixture");
  await page.setViewportSize({ width: 732, height: 336 });
  await page
    .locator("#payment-qr-dialog")
    .screenshot({ path: `${artifacts}/merchant-compact.png` });
  const bounds = await page.locator("#payment-qr-dialog img").boundingBox();
  expect(bounds.y).toBeGreaterThanOrEqual(0);
  expect(bounds.y + bounds.height).toBeLessThanOrEqual(336);
  expect(bounds.width).toBeGreaterThanOrEqual(150);
  await expect(
    page.locator("#payment-qr-dialog [data-qr-copy=back]"),
  ).toBeInViewport();
  await page.keyboard.press("Escape");
  await page.locator("#payment-method").selectOption("CASH");
  await expect(page.locator("#show-payment-qr")).toBeHidden();
});
