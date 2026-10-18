import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

test("ROLE-01 sign-in options stay accessible, responsive and translated", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("radio", { name: /Staff \/ Cashier/ })).toBeChecked();
  await page.getByRole("radio", { name: /^Super Admin/ }).check();
  await expect(page.locator('#login-form [type="submit"]')).toHaveText("Sign in as Super Admin");
  for (const width of [1440, 1024, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(page.locator(".login-roles")).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.setViewportSize({ width: 1440, height: 1000 });
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  await page.screenshot({ path: "test-results/role-login-desktop.png", fullPage: true });
  await page.locator("#login-locale").click();
  await expect(page.locator("html")).toHaveAttribute("lang", "ta");
  await expect(page.locator('#login-form [type="submit"]')).toHaveText("முதன்மை நிர்வாகியாக உள்நுழையவும்");
  await page.setViewportSize({ width: 320, height: 900 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/role-login-mobile-ta.png", fullPage: true });
});

for (const role of ["CASHIER", "ADMIN", "SUPER_ADMIN"]) {
  test(`ROLE-02 ${role} uses its portal and receives only assigned permissions`, async ({ page, request }) => {
    const failures: string[] = [];
    page.on("pageerror", (error) => failures.push(error.message));
    page.on("response", (response) => {
      if (response.status() >= 500) failures.push(`${response.status()} ${new URL(response.url()).pathname}`);
    });
    const password = "Browser-test-password-42!";
    const owner = await request.post("/api/v1/auth/login", {
      headers: { "Idempotency-Key": randomUUID() },
      data: { company_code: "E2E", username: "cashier", password },
    });
    expect(owner.ok()).toBeTruthy();
    const username = `portal-${randomUUID().slice(0, 8)}`;
    const created = await request.post("/api/v1/settings/team", {
      headers: { "Idempotency-Key": randomUUID(), Authorization: `Bearer ${(await owner.json()).access_token}` },
      data: { username, email: `${username}@example.invalid`, full_name: "Portal Trial", role, password, actor_password: password },
    });
    expect(created.status()).toBe(201);
    await page.goto("/login");
    await page.locator('[name="company_code"]').fill("E2E");
    await page.locator('[name="username"]').fill(username);
    await page.locator('[name="password"]').fill(password);
    if (role !== "SUPER_ADMIN") {
      await page.locator('[name="login_role"][value="super_admin"]').check();
      await page.locator('#login-form [type="submit"]').click();
      await expect(page.locator("#login-error")).toContainText("does not have access");
      expect(await page.evaluate(() => sessionStorage.getItem("vglpos.session"))).toBeNull();
    }
    const portal = role === "CASHIER" ? "staff" : role.toLowerCase();
    await page.locator(`[name="login_role"][value="${portal}"]`).check();
    await Promise.all([
      page.waitForURL((url) => url.pathname === (role === "CASHIER" ? "/pos" : "/")),
      page.locator('#login-form [type="submit"]').click(),
    ]);
    const user = await page.evaluate(() => JSON.parse(sessionStorage.getItem("vglpos.session")!).user);
    expect(user.roles).toEqual([role]);
    if (role === "CASHIER") {
      expect(user.permissions).not.toContain("user.manage");
      await expect(page.locator('[data-nav][href="/reports"]')).toBeHidden();
    } else {
      await expect(page.locator('[data-nav][href="/reports"]')).toBeVisible();
    }
    expect(failures).toEqual([]);
  });
}
