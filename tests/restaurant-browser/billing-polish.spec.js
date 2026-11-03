import { test, expect } from "@playwright/test";
import { unlockFixture } from "./access-helper.js";

test("BILLING-POLISH-01 whole counts retain precise drafts, portions and clear confirmation", async ({ page }) => {
  await page.goto("/"); await unlockFixture(page);
  const egg = page.locator('.product-tile[data-product-id="menu-027"]');
  await expect(egg).not.toContainText("Standard");
  await expect(page.locator('[data-product-id="menu-030"]')).toContainText("1/2 kg");
  await egg.click();
  await expect(page.locator('[data-quantity-input="menu-027"]')).toHaveValue("1");
  await expect(page.locator(".cart-line-copy")).not.toContainText("Standard");
  await page.locator('[data-quantity-action="increment"]').click();
  await expect(page.locator('[data-quantity-input="menu-027"]')).toHaveValue("2");
  await expect(page.locator("#draft-status")).toHaveText("Cart saved locally");
  await page.reload();
  await expect(page.locator('[data-quantity-input="menu-027"]')).toHaveValue("2");
  await page.locator("#clear-cart").click();
  await expect(page.locator("#clear-cart-dialog")).toBeVisible();
  await page.locator("#clear-cart-dialog [data-dialog-close]").click();
  await expect(page.locator("#cart-count")).toHaveText("1");
  await page.locator("#clear-cart").click();
  await page.locator("#confirm-clear-cart").click();
  await expect(page.locator("#cart-count")).toHaveText("0");
  await page.locator(".toast").getByRole("button", { name: "Undo" }).click();
  await expect(page.locator('[data-quantity-input="menu-027"]')).toHaveValue("2");
  // Standard must remain identifiable if the owner adds another named portion.
  await page.locator('[data-nav="products"]').click();
  await page.locator("#add-product").click();
  for (const [name,value] of [["name","EGG PORIAL"],["portion","Large"],["category","Egg"],["price","70.00"]])
    await page.locator(`#product-form [name="${name}"]`).fill(value);
  await page.locator('#product-form .button-primary').click();
  await expect(page.locator("#product-dialog")).toBeHidden();
  await page.locator('[data-nav="billing"]').click();
  await expect(egg).toContainText("Standard");
  await expect(page.locator(".cart-line-copy")).toContainText("Standard");
});

for (const [width,height] of [[1920,1080],[1280,720],[1070,716],[800,1280],[390,844],[732,336]]) {
  test(`BILLING-POLISH-02 pinned checkout, breakdown order and bilingual themes at ${width}x${height}`, async ({ page }) => {
    await page.setViewportSize({ width,height });
    await page.goto("/"); await unlockFixture(page);
    for (const id of ["menu-027","menu-028","menu-017","menu-004"])
      await page.locator(`[data-product-id="${id}"]`).click();
    await expect(page.locator("#total-net")).toHaveText("₹425.25");
    await expect(page.locator("#bill-breakdown")).not.toHaveAttribute("open", "");
    const assertFooter = async () => {
      const geometry = await page.evaluate(() => {
        const visible = selector => { const r=document.querySelector(selector).getBoundingClientRect(); return {top:r.top,bottom:r.bottom,left:r.left,right:r.right}; };
        return { total:visible("#total-net"), pay:visible("#pay-button"), overflow:document.documentElement.scrollWidth > innerWidth, viewport:{width:innerWidth,height:innerHeight} };
      });
      expect(geometry.overflow).toBe(false);
      for (const box of [geometry.total,geometry.pay]) { expect(box.top).toBeGreaterThanOrEqual(0); expect(box.bottom).toBeLessThanOrEqual(height); expect(box.left).toBeGreaterThanOrEqual(0); expect(box.right).toBeLessThanOrEqual(width); }
    };
    await assertFooter();
    await page.locator("#bill-breakdown summary").click();
    await expect(page.locator("#total-cgst")).toBeVisible();
    expect(await page.locator("#bill-breakdown dt").allTextContents()).toEqual(["Gross","Discount","Taxable","CGST 2.5%","SGST 2.5%","Round off"]);
    const positions = await page.locator("#bill-breakdown dd").evaluateAll(rows => rows.map(row => ({ top:row.getBoundingClientRect().top,right:row.getBoundingClientRect().right })));
    expect(new Set(positions.map(row => row.right)).size).toBe(1);
    expect(positions.every((row,index) => index===0 || row.top>positions[index-1].top)).toBe(true);
    await assertFooter();
    await page.locator("#bill-breakdown summary").click();
    if (width>=1024) {
      expect(await page.locator("#store-name").evaluate(element => element.getBoundingClientRect().height / parseFloat(getComputedStyle(element).lineHeight))).toBeLessThanOrEqual(2.1);
      await expect(page.locator("#mode-label")).toHaveText("Receipt: Tax invoice");
      await expect(page.locator("#mode-label")).toHaveAttribute("role","status");
    }
    await page.locator("#locale-toggle").click();
    await page.locator("#theme-toggle").click();
    await expect(page.locator("#bill-breakdown summary")).toHaveText("பில் விவரம்");
    await expect(page.locator("#total-net")).toHaveText("₹425.25");
    await assertFooter();
    await page.screenshot({path:`test-results/startup-polish/billing-${width}-dark-ta.png`,fullPage:true});
    await page.locator("#clear-cart").click();
    await expect(page.locator("#clear-cart-title")).toHaveText("இந்தக் கூடையை காலி செய்யவா?");
    await page.locator("#clear-cart-dialog [data-dialog-close]").click();
    await expect(page.locator("#cart-count")).toHaveText("4");
  });
}
