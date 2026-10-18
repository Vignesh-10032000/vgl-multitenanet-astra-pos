import { randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";

for (const role of ["CASHIER", "ADMIN", "SUPER_ADMIN"]) {
  test(`${role} signs in through the supplied form and reaches its portal`, async ({ page, request }) => {
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

    if (role !== "SUPER_ADMIN") {
      const denied = await request.post("/api/v1/auth/login", {
        headers: { "Idempotency-Key": randomUUID() },
        data: { company_code: "E2E", username, password, login_role: "super_admin" },
      });
      expect(denied.ok()).toBe(false);
    }

    await page.goto("/login");
    await page.locator("#company").fill("E2E");
    await page.locator("#user").fill(username);
    await page.locator("#pass").fill(password);
    await Promise.all([
      page.waitForURL((url) => url.pathname === (role === "CASHIER" ? "/pos" : "/")),
      page.locator('#form [type="submit"]').click(),
    ]);
    const user = await page.evaluate(() => JSON.parse(sessionStorage.getItem("vglpos.session")!).user);
    expect(user.roles).toEqual([role]);
    if (role === "CASHIER") {
      expect(user.permissions).not.toContain("user.manage");
    } else {
      expect(user.permissions).toContain("user.manage");
    }
  });
}
