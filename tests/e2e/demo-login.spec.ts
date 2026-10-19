import { expect, test } from "@playwright/test";

test("supplied login design renders and the counter demo works", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/login");

  await expect(page.locator(".hero h1")).toContainText("Run the whole store from one fast counter.");
  await expect(page.locator('img[src="/static/icons/vgl-login-logo.png"]')).toHaveCount(3);
  await expect(page.locator("#prods .prod")).toHaveCount(6);
  await expect(page.locator("#access .rlist .rr")).toHaveCount(7);
  await expect(page.locator("#dashboard .app")).toHaveAttribute("aria-label", "VGL POS dashboard preview with sample data");
  await expect(page.locator("#dashboard .mods .mod")).toHaveCount(9);
  await expect(page.locator('footer nav[aria-label="Product"] a[href="#access"]')).toBeVisible();
  await expect(page.locator("#total")).toContainText("₹519.75");
  await page.locator('[data-add="rice"]').click();
  await expect(page.locator("#total")).toContainText("₹845.25");
  await page.locator("#pay").click();
  await expect(page.locator("#pay")).toContainText("Payment received");
  expect(errors).toEqual([]);

  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
});

test("sign-in validates IDs, toggles password and reports auth errors", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/v1/auth/login", (route) => {
    requests += 1;
    return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Invalid credentials" }) });
  });
  await page.goto("/login");
  await page.locator('#form [type="submit"]').click();
  await expect(page.locator("#company")).toBeFocused();
  expect(requests).toBe(0);

  await page.locator("#company").fill(" E2E ");
  await page.locator("#user").fill(" cashier ");
  await page.locator("#pass").fill("wrong-password");
  await page.locator("#branch").fill("1.5");
  await page.locator('#form [type="submit"]').click();
  await expect(page.locator("#status")).toContainText("positive whole number");
  expect(requests).toBe(0);

  await page.locator("#branch").fill("1");
  await page.locator("#toggle").click();
  await expect(page.locator("#pass")).toHaveAttribute("type", "text");
  await page.locator('#form [type="submit"]').click();
  await expect(page.locator("#status")).toContainText("Invalid credentials");
  expect(requests).toBe(1);
});

test("real sign-in stores the session and follows a safe destination", async ({ page }) => {
  await page.goto("/login?next=%2Freports");
  await page.locator("#company").fill("E2E");
  await page.locator("#user").fill("cashier");
  await page.locator("#pass").fill("Browser-test-password-42!");
  await Promise.all([
    page.waitForURL("**/reports"),
    page.locator('#form [type="submit"]').click(),
  ]);
  await expect(page.getByRole("heading", { name: "Reports", exact: true })).toBeVisible();
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("vglpos.session")!).user.full_name)).toBe("Browser Cashier");
});

test("Explore the demo signs into a populated POS workspace", async ({ page }) => {
  await page.goto("/login?next=%2F#signin");
  await Promise.all([
    page.waitForURL("**/pos"),
    page.locator("#demo-login").click(),
  ]);
  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator("#pos-product-grid button")).toHaveCount(8);
  expect(await page.evaluate(() => JSON.parse(sessionStorage.getItem("vglpos.session")!).user.full_name)).toBe("VGL Demo Explorer");
});

test("demo failure stays at sign-in, blocks duplicate requests and allows retry", async ({ page }) => {
  let requests = 0;
  let releaseFailure!: () => void;
  const failureGate = new Promise<void>((resolve) => { releaseFailure = resolve; });
  await page.route("**/api/v1/auth/demo-login", async (route) => {
    requests += 1;
    await failureGate;
    await route.fulfill({
      status: 503,
      contentType: "application/problem+json",
      body: JSON.stringify({ detail: "Dependency unavailable", request_id: "demo-retry-123" }),
    });
  });
  await page.goto("/login#signin");
  try {
    await page.locator("#demo-login").click();
    await expect(page.locator("#demo-login")).toHaveAttribute("aria-busy", "true");
    await page.locator("#demo-login").dispatchEvent("click");
    await expect.poll(() => requests).toBe(1);
  } finally {
    releaseFailure();
  }
  await expect(page.locator("#status")).toContainText("The demo is temporarily unavailable");
  await expect(page.locator("#status")).toContainText("demo-retry-123");
  await expect(page.locator("#demo-login")).toHaveAttribute("aria-busy", "false");
  expect(new URL(page.url()).hash).toBe("#signin");
  expect(await page.evaluate(() => sessionStorage.getItem("vglpos.session"))).toBeNull();

  await page.unroute("**/api/v1/auth/demo-login");
  await Promise.all([
    page.waitForURL("**/pos"),
    page.locator("#demo-login").click(),
  ]);
});
