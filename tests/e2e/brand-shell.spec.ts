import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

test("public login preserves the supplied business site and billing story", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator("#c-web")).toHaveAttribute("href", "https://vigneshgrowthlab.dev");
  await expect(page.locator("#c-web")).toHaveAttribute("target", "_blank");
  await expect(page.getByRole("heading", { name: "Fast billing", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "One company, many tills", exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.screenshot({ path: "test-results/brand-login-desktop.png", fullPage: true });
});

test("dashboard styling and accessible navigation carry across the POS workspace", async ({ page, request }) => {
  const login = await request.post("/api/v1/auth/demo-login", {
    data: {}, headers: { "Idempotency-Key": randomUUID() },
  });
  expect(login.ok()).toBeTruthy();
  const session = await login.json();
  await page.addInitScript((value) => {
    sessionStorage.setItem("vglpos.session", JSON.stringify(value));
  }, session);

  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  for (const width of [1440, 900, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const routes = await page.locator(".side-nav nav a:visible").evaluateAll(
      (links) => links.map((link) => (link as HTMLAnchorElement).getAttribute("href")!),
    );
    for (const route of routes) {
      await page.goto(route);
      await expect(page.locator(".brand-logo")).toHaveJSProperty("naturalWidth", 701);
      await expect(page.locator(`[data-nav][href="${route}"]`)).toHaveClass(/is-active/);
      await expect(page.locator("i[data-lucide]:visible"), `${route} at ${width}px has a missing icon`).toHaveCount(0);
      const layout = await page.evaluate(() => {
        const nav = document.querySelector(".side-nav nav")!;
        const active = nav.querySelector(".is-active")!;
        const navBox = nav.getBoundingClientRect();
        const activeBox = active.getBoundingClientRect();
        return {
          palette: getComputedStyle(document.body).getPropertyValue("--primary").trim(),
          overflow: document.documentElement.scrollWidth > innerWidth + 1,
          scrollWidth: document.documentElement.scrollWidth,
          navRows: nav.scrollHeight > nav.clientHeight + 2,
          activeVisible: activeBox.left >= navBox.left - 1 && activeBox.right <= navBox.right + 1,
        };
      });
      expect(layout.palette, `${route} at ${width}px`).toBe("#073f7d");
      expect(layout.overflow, `${route} at ${width}px: ${JSON.stringify(layout)}`).toBe(false);
      if (width <= 720) {
        expect(layout.navRows, `${route} at ${width}px`).toBe(false);
        expect(layout.activeVisible, `${route} at ${width}px`).toBe(true);
        await expect(page.getByRole("link", { name: "Reports" })).toHaveCount(1);
      }
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/pos");
  await expect(page.locator("#pos-product-grid")).toHaveAttribute("aria-busy", "false");
  await expect(page.locator("#pos-product-grid button")).toHaveCount(8);
  await expect(page.locator("#shift-status span")).toBeVisible();
  await expect(page.locator("#scanner-status span")).toBeVisible();
  const quickKeyGap = await page.locator(".quick-key-button").first().evaluate((button) => {
    const key = button.querySelector("kbd")!.getBoundingClientRect();
    const name = button.querySelector("span")!.getBoundingClientRect();
    return name.left - key.right;
  });
  expect(quickKeyGap).toBeGreaterThanOrEqual(4);
  await page.screenshot({ path: "test-results/brand-pos-mobile.png", fullPage: true });
  expect(pageErrors).toEqual([]);
});
