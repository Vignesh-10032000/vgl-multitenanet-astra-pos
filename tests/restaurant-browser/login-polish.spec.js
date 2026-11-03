import { test, expect } from "@playwright/test";
import { unlockFixture } from "./access-helper.js";

test("LOGIN-POLISH-01 password toggle, cursor, empty username, Enter and loading/error states", async ({ page }) => {
  await page.goto("/");
  await unlockFixture(page);
  await page.locator("#lock-workspace").click();
  await expect(page.locator("#access-username")).toHaveValue("");
  await page.locator("#access-username").fill("test-owner");
  const password = page.locator("#access-password");
  await password.fill("wrong-password");
  await password.evaluate(input => input.setSelectionRange(2, 7, "forward"));
  const toggle = page.locator("#access-password-toggle");
  await expect(toggle).toHaveAttribute("type", "button");
  await toggle.click();
  await expect(password).toHaveAttribute("type", "text");
  await expect(toggle).toHaveAttribute("aria-label", "Hide password");
  expect(await password.evaluate(input => [input.selectionStart, input.selectionEnd])).toEqual([2, 7]);
  await toggle.click();
  await expect(password).toHaveValue("wrong-password");
  await password.press("Enter");
  await expect(page.locator("#access-submit")).toBeDisabled();
  await expect(page.locator("#access-submit")).toHaveText("Signing in…");
  await expect(page.locator("#access-error")).toHaveText("Username or password is incorrect");
  await password.fill("Fixture-only-owner-482!");
  await page.locator("#access-username").press("Enter");
  await expect(page.locator("#access-screen")).toBeHidden();
  await page.locator("#lock-workspace").click();
  await expect(page.locator("#access-username")).toHaveValue("");
});

for (const [width, height] of [[1920,1080], [1070,716], [800,1280], [390,844]]) {
  test(`LOGIN-POLISH-02 bilingual light/dark geometry and helper contrast at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.addInitScript(() => { localStorage.setItem("vglpos.locale", "ta"); localStorage.setItem("vglpos.theme", "dark"); });
    await page.goto("/");
    await expect(page.locator("#access-submit")).toBeEnabled();
    await expect(page.locator("#access-password-toggle")).toHaveAttribute("aria-label", "கடவுச்சொல்லைக் காட்டு");
    await expect(page.locator(".access-footnote").last()).toContainText("இணையமின்றி");
    for (const theme of ["dark", "light"]) {
      await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      const geometry = await page.evaluate(() => {
        const rect = selector => document.querySelector(selector).getBoundingClientRect();
        const ratio = selector => {
          const color = getComputedStyle(document.querySelector(selector)).color.match(/[\d.]+/g).slice(0,3).map(Number);
          const surface = getComputedStyle(document.querySelector(".access-screen")).backgroundColor.match(/[\d.]+/g).slice(0,3).map(Number);
          const luminance = c => c.map(v => { v /= 255; return v <= 0.04045 ? v/12.92 : ((v+0.055)/1.055)**2.4; }).reduce((sum,v,i) => sum + v*[0.2126,0.7152,0.0722][i], 0);
          const a=luminance(color), b=luminance(surface);
          return (Math.max(a,b)+0.05)/(Math.min(a,b)+0.05);
        };
        return { overflow: document.documentElement.scrollWidth > innerWidth, fieldLeft: rect("#access-username").left, recoveryLeft: rect(".access-recovery").left, linkLeft: rect("#access-recover").left, toggle: { w: rect("#access-password-toggle").width, h: rect("#access-password-toggle").height }, helpers: [".access-recovery", "#access-recover", ".access-footnote:last-of-type", ".vgl-brand-access .vgl-brand-credit"].map(selector => ({ size: parseFloat(getComputedStyle(document.querySelector(selector)).fontSize), ratio: ratio(selector) })) };
      });
      expect(geometry.overflow).toBe(false);
      expect(geometry.recoveryLeft).toBe(geometry.fieldLeft);
      expect(geometry.linkLeft).toBe(geometry.fieldLeft);
      expect(geometry.toggle.w).toBeGreaterThanOrEqual(44);
      expect(geometry.toggle.h).toBeGreaterThanOrEqual(44);
      for (const helper of geometry.helpers) { expect(helper.size).toBeGreaterThanOrEqual(13); expect(helper.ratio).toBeGreaterThanOrEqual(4.5); }
      await page.locator("#access-username").focus();
      expect(await page.locator("#access-username").evaluate(input => getComputedStyle(input).outlineStyle)).toBe("solid");
      await page.screenshot({ path: `test-results/startup-polish/login-${width}-${theme}.png`, fullPage: true });
    }
  });
}
