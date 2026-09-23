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
}

async function closeExistingShift(page) {
  const result = await page.evaluate(async () => {
    const session = JSON.parse(sessionStorage.getItem("vglpos.session") || "null");
    const headers = {
      Accept: "application/json",
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    };
    const current = await fetch("/api/v1/shifts/current", { headers }).then((response) => response.json());
    if (!current.shift) return { status: 204 };
    const report = await fetch(`/api/v1/shifts/${current.shift.id}/z-report`, { headers })
      .then((response) => response.json());
    const values = [2000, 500, 200, 100, 50, 20, 10, 5, 2, 1];
    let remaining = Number.parseInt(report.expected_cash, 10);
    const denomination_counts = {};
    values.forEach((value) => {
      const count = Math.floor(remaining / value);
      if (count) denomination_counts[String(value)] = count;
      remaining %= value;
    });
    const response = await fetch("/api/v1/shifts/close", {
      method: "POST",
      headers,
      body: JSON.stringify({
        shift_id: current.shift.id,
        counted_cash: report.expected_cash,
        denomination_counts,
        expire_held_bills: true,
      }),
    });
    return { status: response.status, body: await response.text() };
  });
  expect(result.status, result.body).toBe(200);
}

async function scan(page, barcode: string) {
  await page.evaluate((value) => {
    for (const key of value) {
      document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  }, barcode);
}

test("cashier opens, sells, blind-closes, and prints a complete Z report", async ({ page }) => {
  await signIn(page);
  if (await page.locator("#shift-open-dialog").isVisible()) {
    await page.locator('#shift-open-form [data-denomination="100"]').fill("1");
    await page.locator("#shift-open-form").getByRole("button", { name: /open shift/i }).click();
    await expect(page.locator("#shift-open-dialog")).toBeHidden();
  }
  await closeExistingShift(page);

  await page.reload();
  await expect(page.locator("#shift-open-dialog")).toBeVisible();
  await page.locator('#shift-open-form [data-denomination="100"]').fill("1");
  await expect(page.locator('#shift-open-form [data-denomination-total]')).toHaveText("₹100.00");
  await page.locator("#shift-open-form").getByRole("button", { name: /open shift/i }).click();
  await expect(page.locator("#shift-status")).toHaveAttribute("data-state", "open");

  await scan(page, "8901234567890");
  await expect(page.locator("#total-net")).toHaveText("₹118.00");
  await page.keyboard.press("F2");
  await page.locator('[data-cash="exact"]').click();
  await Promise.all([
    page.waitForURL(/\/receipt\/\d+/),
    page.locator("#complete-sale").click(),
  ]);
  await page.getByRole("link", { name: /new sale/i }).click();
  await expect(page).toHaveURL(/\/pos$/);
  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator("#shift-status")).toHaveAttribute("data-state", "open");

  await page.keyboard.press("F10");
  await expect(page.locator("#shift-close-dialog")).toBeVisible();
  const closeForm = page.locator("#shift-close-form");
  for (const [denomination, count] of [["200", "1"], ["10", "1"], ["5", "1"], ["2", "1"], ["1", "1"]]) {
    await closeForm.locator(`[data-denomination="${denomination}"]`).fill(count);
  }
  await expect(closeForm.locator("[data-denomination-total]")).toHaveText("₹218.00");
  await Promise.all([
    page.waitForURL(/\/z-report\/\d+/),
    closeForm.getByRole("button", { name: /close shift/i }).click(),
  ]);

  await expect(page.locator("#z-report")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator("#z-transactions")).toHaveText("1");
  await expect(page.locator("#z-net-sales")).toHaveText("₹118.00");
  await expect(page.locator("#z-expected-cash")).toHaveText("₹218.00");
  await expect(page.locator("#z-counted-cash")).toHaveText("₹218.00");
  await expect(page.locator("#z-variance")).toHaveText("₹0.00");
  await expect(page.locator("#print-z-report")).toBeVisible();
});
