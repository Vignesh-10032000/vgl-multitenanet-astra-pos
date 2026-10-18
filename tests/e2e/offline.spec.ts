import { expect, test } from "@playwright/test";

async function signIn(page) {
  await page.goto("/login");
  await page.locator("#company").fill("E2E");
  await page.locator("#user").fill("cashier");
  await page.locator("#pass").fill("Browser-test-password-42!");
  await page.locator("#branch").fill("1");
  await page.locator("#terminal").fill("1");
  await Promise.all([
    page.waitForURL("**/pos"),
    page.locator("#form").getByRole("button", { name: /sign in/i }).click(),
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

async function saleItems(page) {
  return page.evaluate(async () => {
    const session = JSON.parse(sessionStorage.getItem("vglpos.session") || "null");
    const response = await fetch("/api/v1/sales?limit=200", {
      headers: { Authorization: `Bearer ${session.access_token}` },
    });
    return (await response.json()).items;
  });
}

async function saleCount(page) {
  return (await saleItems(page)).length;
}

async function scan(page, barcode: string) {
  await page.evaluate((value) => {
    for (const key of value) {
      document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    }
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  }, barcode);
}

test("offline bill receives a provisional receipt and syncs exactly once", async ({ page, context }) => {
  await signIn(page);
  const initialItems = await saleItems(page);
  const initialIds = new Set(initialItems.map((sale) => sale.id));
  const initialSales = initialItems.length;

  await page.waitForFunction(async () => {
    await navigator.serviceWorker.ready;
    return new Promise((resolve) => {
      const request = indexedDB.open("vglpos-offline", 1);
      request.onsuccess = () => {
        const transaction = request.result.transaction(["products", "meta"], "readonly");
        const products = transaction.objectStore("products").count();
        const facts = transaction.objectStore("meta").get("offline-facts");
        transaction.oncomplete = () => resolve(products.result > 0 && Boolean(facts.result));
      };
      request.onerror = () => resolve(false);
    });
  });

  await context.setOffline(true);
  await expect(page.locator("#connectivity-label")).toContainText("Offline");
  await scan(page, "8901234567890");
  await expect(page.locator('[data-quantity-input="1"]')).toHaveValue("1.000");
  await expect(page.locator("#total-net")).toHaveText("₹118.00");

  await page.keyboard.press("F2");
  await page.locator('[data-cash="exact"]').click();
  await expect(page.locator("#payment-balance")).toHaveText("₹0.00");
  await expect(page.locator("#complete-sale")).toBeEnabled();
  await Promise.all([
    page.waitForURL(/\/receipt\/offline\/[0-9a-f-]+/),
    page.locator("#complete-sale").click(),
  ]);
  await expect(page.locator(".provisional-banner")).toBeVisible();
  await expect(page.locator("#receipt-number")).toContainText("WEB-01-OFF-");
  await expect(page.locator("#receipt-total")).toHaveText("₹118.00");

  await context.setOffline(false);
  await expect.poll(async () => saleCount(page), { timeout: 20_000 }).toBe(initialSales + 1);
  await expect.poll(async () => page.evaluate(async () => {
    return new Promise((resolve) => {
      const request = indexedDB.open("vglpos-offline", 1);
      request.onsuccess = () => {
        const count = request.result.transaction("outbox", "readonly")
          .objectStore("outbox").count();
        count.onsuccess = () => resolve(count.result);
      };
      request.onerror = () => resolve(-1);
    });
  })).toBe(0);

  const newest = (await saleItems(page)).find((sale) => !initialIds.has(sale.id));
  expect(newest).toBeDefined();
  expect(newest.net_amount).toBe("118.00");
  expect(newest.invoice_number).toContain("WEB/");
});
