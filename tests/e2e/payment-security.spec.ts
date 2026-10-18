import { createHmac, randomUUID } from "node:crypto";
import path from "node:path";
import { expect, test } from "@playwright/test";

const password = "Browser-test-password-42!";

async function signIn(page, username = "cashier", credential = password, counter = true) {
  await page.goto("/login");
  await page.locator("#company").fill("E2E");
  await page.locator("#user").fill(username);
  await page.locator("#pass").fill(credential);
  await page.locator("#branch").fill("1");
  await page.locator("#terminal").fill("1");
  await page.locator('#form [type="submit"]').click();
  await page.waitForURL("**/pos");
  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
  if (!counter) return;
  await page.waitForFunction(() => document.querySelector("#shift-open-dialog")?.open || document.querySelector("#shift-status")?.getAttribute("data-state") === "open");
  if (await page.locator("#shift-open-dialog").isVisible()) {
    await page.locator('#shift-open-form [data-denomination="100"]').fill("1");
    await page.locator('#shift-open-form [type="submit"]').click();
    await expect(page.locator("#shift-open-dialog")).toBeHidden();
  }
}

async function scanRice(page) {
  await page.evaluate(() => {
    for (const key of "8901234567890") document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  });
  await expect(page.locator("#total-net")).toHaveText("₹118.00");
}

test("PAY-03 payment defaults to the bill and stale previews never override edited tender", async ({ page }) => {
  await signIn(page);
  await scanRice(page);
  await page.locator("#pay-button").click();
  await expect(page.locator("[data-payment-amount]")).toHaveValue("118.00");
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.route("**/api/v1/sales/payment-preview", async (route) => {
    const response = await route.fetch();
    if (route.request().postDataJSON().payments[0]?.amount === "100.00") await new Promise((resolve) => setTimeout(resolve, 900));
    await route.fulfill({ response });
  });
  const shortPreview = page.waitForRequest((request) => request.url().endsWith("/payment-preview") && request.postDataJSON().payments[0].amount === "100.00");
  await page.locator("[data-payment-amount]").fill("100.00");
  await expect(page.locator("#complete-sale")).toBeDisabled();
  await expect(page.locator("#payment-outcome-label")).toHaveText("Still to collect");
  await expect(page.locator("#payment-change")).toHaveText("₹18.00");
  await expect(page.locator("#payment-balance")).toHaveText("₹18.00");
  await shortPreview;
  await page.locator("[data-payment-amount]").fill("500.00");
  await expect(page.locator("#payment-change")).toHaveText("₹382.00");
  await expect(page.locator("#payment-outcome-label")).toHaveText("Change to return");
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.waitForTimeout(1000);
  await expect(page.locator("#payment-balance")).toHaveText("₹0.00");
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.screenshot({ path: "test-results/payment-change-desktop.png" });
  await page.locator("[data-payment-amount]").fill("100.00");
  await page.locator("#add-payment-row").click();
  await expect(page.locator("[data-payment-amount]").nth(1)).toHaveValue("18.00");
  await page.locator("[data-payment-reference]").nth(1).fill("UPI-SPLIT-TEST");
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.locator('[data-cash="exact"]').click();
  await expect(page.locator("[data-payment-amount]").first()).toHaveValue("100.00");
  await expect(page.locator("#payment-received")).toHaveText("₹118.00");
});

test("BRAND-03 uploaded store logo and receipt date, time and numeric columns render on every paper", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings");
  await expect(page.locator('[data-tab-panel="store"]')).toBeHidden();
  await page.locator('[data-tab-target="store"]').click();
  await page.locator("#store-logo-file").setInputFiles(path.resolve("src/vglpos/web/static/icons/vgl-logo.png"));
  await expect(page.locator("#store-logo-preview")).toBeVisible();
  await expect(page.locator("#remove-store-logo")).toBeEnabled();
  await page.reload();
  await page.locator('[data-tab-target="store"]').click();
  await expect(page.locator("#store-logo-preview")).toBeVisible();
  await page.goto("/pos");
  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
  await scanRice(page);
  await page.locator('.product-tile[data-product-id="2"]').click();
  for (const key of ["0", ".", "2", "5"]) await page.locator(`#weight-keypad [data-key="${key}"]`).click();
  await page.locator("#weight-dialog").getByRole("button", { name: "Add weight" }).click();
  await expect(page.locator("#total-net")).toHaveText("₹136.00");
  await page.locator("#pay-button").click();
  await page.locator('[data-cash="500"]').click();
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await page.locator("#complete-sale").click();
  await page.waitForURL(/\/receipt\/\d+/);
  await expect(page.locator("#invoice")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator("#receipt-store-logo")).toBeVisible();
  await expect(page.locator("#receipt-date")).not.toContainText(/am|pm/i);
  await expect(page.locator("#receipt-time")).toContainText(/am|pm/i);
  await expect(page.locator("#receipt-payments")).toContainText("₹364.00");
  await expect(page.locator("#receipt-lines")).toContainText("0.25");
  for (const paper of ["58", "80", "a5"]) {
    await page.locator(`[data-paper-value="${paper}"]`).click();
    const spacing = await page.locator("#receipt-lines tr").last().evaluate((row) => {
      const cells = [...row.querySelectorAll("td")];
      return cells.map((cell) => ({ left: cell.getBoundingClientRect().left, right: cell.getBoundingClientRect().right, width: cell.clientWidth, content: cell.scrollWidth }));
    });
    expect(spacing.every((cell) => cell.content <= cell.width + 1)).toBe(true);
    expect(spacing[1].right).toBeLessThanOrEqual(spacing[2].left + 1);
    await page.locator("#invoice").screenshot({ path: `test-results/receipt-aligned-${paper}.png` });
  }
});

test("SEC-06 team accounts sign in with server-assigned cashier permissions", async ({ page, browser }) => {
  await signIn(page);
  await page.goto("/settings");
  await page.locator('[data-tab-target="team"]').click();
  await expect(page.locator("#team-new")).toBeVisible();
  await page.locator("#team-new").click();
  const form = page.locator("#team-form");
  const username = `staff-${randomUUID().slice(0, 8)}`;
  await form.locator('[name="full_name"]').fill("New Cashier");
  await form.locator('[name="username"]').fill(username);
  await form.locator('[name="email"]').fill(`${username}@example.invalid`);
  await form.locator('[name="role"]').selectOption("CASHIER");
  await form.locator('[name="password"]').fill("New cashier password 42!");
  await form.locator('[name="pin"]').fill("753159");
  await form.locator('[name="actor_password"]').fill(password);
  await form.locator('[type="submit"]').click();
  await expect(page.locator("#team-dialog")).toBeHidden();
  await expect(page.locator("#team-rows")).toContainText(username);
  const context = await browser.newContext();
  const staff = await context.newPage();
  await signIn(staff, username, "New cashier password 42!", false);
  await expect(staff.locator('[data-nav="reports"]')).toBeHidden();
  await expect(staff.locator('[data-nav="pos"]')).toBeVisible();
  await staff.goto("/settings");
  await expect(staff.locator('[data-tab-target="team"]')).toBeHidden();
  await expect(staff.locator('[data-tab-target="store"]')).toBeHidden();
  await staff.locator('[data-tab-target="security"]').click();
  await expect(staff.locator("#security-role")).toHaveText("Cashier");
  await context.close();
});

function totp(secret: string) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bits = [...secret].map((letter) => alphabet.indexOf(letter).toString(2).padStart(5, "0")).join("");
  const key = Buffer.from(bits.match(/.{8}/g)!.map((byte) => parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const hash = createHmac("sha1", key).update(counter).digest();
  const offset = hash.at(-1)! & 15;
  return String((hash.readUInt32BE(offset) & 0x7fffffff) % 1000000).padStart(6, "0");
}

test("SEC-07 administrator can enroll an authenticator and sign out every device", async ({ page }) => {
  await signIn(page);
  await page.goto("/settings");
  await page.locator('[data-tab-target="security"]').click();
  await page.locator('#mfa-setup-form [name="password"]').fill(password);
  await page.locator('#mfa-setup-form [type="submit"]').click();
  await expect(page.locator("#mfa-enable-form")).toBeVisible();
  const secret = await page.locator("#mfa-secret").inputValue();
  await page.locator('#mfa-enable-form [name="code"]').fill(totp(secret));
  await page.locator('#mfa-enable-form [type="submit"]').click();
  await expect(page.locator("#mfa-status")).toHaveText("Authenticator enabled");
  await expect(page.locator("#mfa-setup-form")).toBeHidden();
  await page.evaluate(() => scrollTo(0, 0));
  await page.screenshot({ path: "test-results/security-settings-desktop.png", fullPage: true });
  await page.locator('#mfa-disable-form [name="code"]').fill(totp(secret));
  await page.locator('#mfa-disable-form [type="submit"]').click();
  await expect(page.locator("#mfa-status")).toHaveText("Authenticator not enabled");
  await page.locator('#logout-all-form [name="password"]').fill(password);
  await page.locator('#logout-all-form [type="submit"]').click();
  await page.waitForURL("**/login");
});

test("REPORT-01 reports explain the selected dates and remain aligned in both themes", async ({ page }) => {
  await signIn(page);
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  for (const width of [1440, 900, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/reports");
    await expect(page.locator("#report-date-range")).not.toBeEmpty();
    await expect(page.getByText("Total sales", { exact: true })).toBeVisible();
    await expect(page.getByText("Bills completed", { exact: true })).toBeVisible();
    const labelsClear = await page.locator(".bar-column").first().evaluate((column) => column.querySelector(".bar-value")!.getBoundingClientRect().bottom <= column.querySelector(".bar-plot")!.getBoundingClientRect().top);
    expect(labelsClear).toBe(true);
    for (const theme of ["light", "dark"]) {
      await page.evaluate((value) => { document.documentElement.dataset.theme = value; }, theme);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    }
    if (width === 1440) await page.screenshot({ path: "test-results/reports-overview-desktop.png" });
  }
  expect(errors).toEqual([]);
});
