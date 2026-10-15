import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("login preview is complete, accessible and fills the desktop layout", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/login");
  await expect(page.getByText("Illustrative sample data")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Build repeat business" })).toBeVisible();
  await expect(page.locator(".sample-bill-total")).toContainText("₹519.75");
  await expect(page.locator(".sample-product")).toHaveCount(3);
  for (const width of [1920, 1440, 1100]) {
    await page.setViewportSize({ width, height: 1080 });
    const form = await page.locator(".login-panel").boundingBox();
    const visual = await page.locator(".login-visual").boundingBox();
    expect(Math.abs(form.x + form.width - visual.x)).toBeLessThan(2);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1080 });
  const accessibility = await new AxeBuilder({ page }).analyze();
  expect(accessibility.violations).toEqual([]);
  await page.screenshot({ path: "test-results/login-desktop.png", fullPage: true });
});

test("mobile sign-in fields fill the form without horizontal scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Explore the demo" })).toBeVisible();
  const username = await page.locator('[name="username"]').boundingBox();
  const form = await page.locator("#login-form").boundingBox();
  expect(Math.abs(username.width - form.width)).toBeLessThan(2);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/login-mobile.png", fullPage: true });
});

test("login branding, contact actions and feature highlights stay usable across widths", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/login");
  for (const width of [320, 390, 768, 1024, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.getByRole("img", { name: "Vignesh Growth Lab" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Need a POS tailored to your store?" })).toBeVisible();
    await expect(page.getByRole("link", { name: "vigneshgrowthlab@gmail.com" })).toHaveAttribute("href", "mailto:vigneshgrowthlab@gmail.com");
    await expect(page.getByRole("link", { name: "WhatsApp" })).toHaveAttribute("href", "https://wa.me/918220034139");
    await expect(page.getByRole("link", { name: /Call \+91/ })).toHaveAttribute("href", "tel:+918220034139");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (width > 1000) {
      await expect(page.getByText("Barcode scan & quick keys")).toBeVisible();
      await expect(page.getByText("Hold & recall bills")).toBeVisible();
      await expect(page.getByText("Split payments")).toBeVisible();
      await expect(page.getByText("Offline bill queue")).toBeVisible();
    }
  }
  expect(errors).toEqual([]);
});

test("sign-in validates input and password toggle announces its state", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/v1/auth/login", (route) => {
    requests += 1;
    return route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: "Invalid credentials" }) });
  });
  await page.goto("/login");
  await page.locator('#login-form button[type="submit"]').click();
  await expect(page.locator('[name="company_code"]')).toBeFocused();
  expect(requests).toBe(0);
  await page.locator('[name="company_code"]').fill(" E2E ");
  await page.locator('[name="username"]').fill(" cashier ");
  await page.locator('[name="password"]').fill("wrong-password");
  await page.locator('[name="branch_id"]').fill("1.5");
  await page.locator('#login-form button[type="submit"]').click();
  expect(requests).toBe(0);
  await page.locator('[name="branch_id"]').fill("1");
  await page.getByRole("button", { name: "Show password" }).click();
  await expect(page.getByRole("button", { name: "Hide password" })).toBeVisible();
  await expect(page.locator('[name="password"]')).toHaveAttribute("type", "text");
  await page.locator('#login-form button[type="submit"]').click();
  await expect(page.locator("#login-error")).toContainText("Invalid credentials");
  expect(requests).toBe(1);
});

test("Tamil login remains readable at narrow width", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.goto("/login");
  await page.locator("#login-locale").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ta");
  await expect(page.locator("#login-contact-title")).toContainText("POS");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("saved Tamil preference labels the language and password controls correctly", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("vglpos.locale", "ta"));
  await page.goto("/login");
  await expect(page.locator("html")).toHaveAttribute("lang", "ta");
  await expect(page.locator("#login-locale")).toContainText("EN");
  await expect(page.locator("#password-toggle")).toHaveAttribute("aria-label", "கடவுச்சொல்லைக் காண்பி");
});

test("saved dark preference keeps the branded sign-in panel readable", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("vglpos.theme", "dark"));
  await page.goto("/login");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const colors = await page.locator(".login-panel").evaluate((panel) => ({
    background: getComputedStyle(panel).backgroundColor,
    title: getComputedStyle(panel.querySelector("h1")!).color,
  }));
  expect(colors.background).toBe("rgb(255, 255, 255)");
  expect(colors.title).toBe("rgb(7, 45, 94)");
});

test("store team can sign in and follow a same-origin destination", async ({ page }) => {
  await page.goto("/login?next=%2Freports");
  await page.locator('[name="company_code"]').fill("E2E");
  await page.locator('[name="username"]').fill("cashier");
  await page.locator('[name="password"]').fill("Browser-test-password-42!");
  await Promise.all([
    page.waitForURL("**/reports"),
    page.locator('#login-form button[type="submit"]').click(),
  ]);
  await expect(page.getByRole("heading", { name: "Reports", exact: true })).toBeVisible();
});

for (const status of [500, 503]) {
  test(`demo outage ${status} shows a helpful message and support reference`, async ({ page }) => {
    await page.goto("/login");
    await page.route("**/api/v1/auth/demo-login", (route) => route.fulfill({
      status,
      contentType: "application/problem+json",
      body: JSON.stringify({ detail: "An unexpected error occurred.", request_id: "demo-support-123" }),
    }));
    await page.getByRole("button", { name: "Explore the demo" }).click();
    await expect(page.locator("#demo-error")).toContainText("The demo is temporarily unavailable");
    await expect(page.locator("#demo-error")).toContainText("Support reference: demo-support-123");
    await expect(page.locator("#login-error")).toBeEmpty();
    await expect(page.getByRole("button", { name: "Explore the demo" })).toBeEnabled();
    await expect(page.locator('#login-form button[type="submit"]')).toBeEnabled();
  });
}

test("demo network failure allows retry", async ({ page }) => {
  await page.goto("/login");
  await page.route("**/api/v1/auth/demo-login", (route) => route.abort("failed"));
  await page.getByRole("button", { name: "Explore the demo" }).click();
  await expect(page.locator("#demo-error")).toContainText("Check your internet connection");
  await expect(page.getByRole("button", { name: "Explore the demo" })).toBeEnabled();
});

test("demo waits for initialization before accepting clicks", async ({ page }) => {
  let releaseLocale;
  const localeGate = new Promise((resolve) => { releaseLocale = resolve; });
  await page.route("**/static/i18n/en.json", async (route) => {
    await localeGate;
    await route.continue();
  });
  try {
    await page.goto("/login");
    await expect(page.locator("#demo-login")).toBeDisabled();
  } finally {
    releaseLocale();
  }
  await expect(page.locator("#demo-login")).toBeEnabled();
  await Promise.all([
    page.waitForURL("**/pos"),
    page.locator("#demo-login").click(),
  ]);
  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
});

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
  await expect(page.locator("#recent-sales tr")).toHaveCount(8);
});
