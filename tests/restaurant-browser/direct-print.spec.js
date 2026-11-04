import { test, expect } from "@playwright/test";
import { unlockFixture } from "./access-helper.js";

test("DIRECT-PRINT-01 saved receipt survives USB success, failure and cancellation without another bill", async ({ page }) => {
  await page.addInitScript(() => {
    window.Capacitor = { PluginHeaders: [
      { name: "RestaurantPrinter", methods: [{ name: "printReceipt", rtype: "promise" }, { name: "openPrinterSetup", rtype: "promise" }] },
      { name: "RestaurantDocuments", methods: [{ name: "printReceipt", rtype: "promise" }] },
    ] };
  });
  await page.goto("/");
  await unlockFixture(page);
  await page.locator('[data-product-id="menu-001"]').click();
  await expect(page.locator("#total-net")).toHaveText("₹178.50");
  await page.locator("#pay-button").click();
  await page.locator("#complete-sale").click();
  const receipt = page.locator("#receipt-preview .receipt-paper");
  await expect(receipt.locator(".net")).toHaveText("TOTAL₹178.50");
  const saved = await receipt.innerHTML();
  await page.evaluate(() => {
    window.printCalls = [];
    window.printResult = "submitted";
    window.Capacitor.getPlatform = () => "android";
    window.Capacitor.isNativePlatform = () => true;
    window.Capacitor.nativePromise = async (plugin, method, options) => {
      window.printCalls.push({ plugin, method, options });
      if (window.printResult === "failed") throw new Error("USB disconnected; check paper before reprinting");
      if (window.printResult === "service_disabled") throw new Error("Configure and enable ESC POS USB Print Service in Printer setup");
      return { state: plugin === "RestaurantDocuments" ? "submitted" : window.printResult };
    };
  });
  // Refresh the receipt controls after switching the mock platform to Android.
  await page.locator('#receipt-dialog [data-close]').click();
  await page.locator("#last-receipt").click();
  await expect(page.locator("#print-receipt")).toHaveText("Print to USB");
  await expect(page.locator("#print-service-receipt")).toBeVisible();
  await expect(page.locator("#printer-setup")).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 720 });
  expect(await page.locator("#receipt-dialog .dialog-actions").evaluate(actions => actions.scrollWidth > actions.clientWidth)).toBe(false);
  for (const state of ["submitted", "failed", "cancelled"]) {
    await page.evaluate(value => { window.printResult = value; }, state);
    await page.locator("#print-receipt").click();
    await expect(page.locator("#print-receipt")).toBeEnabled();
    await expect(page.locator("#print-status")).toContainText(state === "failed" ? "Bill remains saved. Printing failed" : state === "cancelled" ? "Print cancelled. Bill remains saved" : "Print submitted");
    expect(await receipt.innerHTML()).toBe(saved);
  }
  // A failed/cancelled USB attempt must never silently open Android's Save as PDF panel.
  expect(await page.evaluate(() => window.printCalls.filter(call => call.plugin === "RestaurantDocuments").length)).toBe(0);
  await page.evaluate(() => { window.printResult = "submitted"; });
  await page.locator("#printer-setup").click();
  await expect.poll(() => page.evaluate(() => window.printCalls.filter(call => call.method === "openPrinterSetup").length)).toBe(1);
  await page.locator("#print-service-receipt").click();
  await expect(page.locator("#print-receipt")).toBeEnabled();
  await expect(page.locator("#print-status")).toContainText("Print submitted");
  await page.evaluate(() => { window.printResult = "service_disabled"; });
  await page.locator("#print-service-receipt").click();
  await expect(page.locator("#print-status")).toContainText("Configure and enable ESC POS USB Print Service");
  const calls = await page.evaluate(() => window.printCalls);
  expect(calls.filter(call => call.plugin === "RestaurantPrinter" && call.method === "printReceipt")).toHaveLength(3);
  expect(calls.filter(call => call.plugin === "RestaurantDocuments")).toHaveLength(2);
  const payload = calls[0].options.html;
  const markup = await page.evaluate(html => new DOMParser().parseFromString(html, "text/html").querySelector(".receipt-paper").innerHTML, payload);
  expect(markup).toBe(saved);
  expect(payload).toContain('rel="stylesheet"');
  expect(payload).toContain('src="data:image/jpeg;base64,');
  // Exercise the exact isolated document/CSP offline, in addition to the existing preview checks.
  await page.evaluate(html => {
    const frame = document.createElement("iframe");
    frame.id = "direct-print-fixture";
    frame.style.width = "80mm";
    frame.srcdoc = html;
    document.body.append(frame);
  }, payload);
  const isolated = page.frameLocator("#direct-print-fixture");
  await expect(isolated.locator(".receipt-paper .net")).toHaveText("TOTAL₹178.50");
  const rendering = await isolated.locator(".receipt-paper").evaluate(async paper => {
    await document.fonts.ready;
    await Promise.all([...document.images].map(image => image.decode()));
    const rate = paper.querySelector("thead th:nth-child(3)").getBoundingClientRect();
    const tax = paper.querySelector('[data-receipt-total="cgst"] .receipt-summary-value').getBoundingClientRect();
    return { height: paper.getBoundingClientRect().height, aligned: Math.abs(rate.right - tax.right) < 0.5, overflow: paper.scrollWidth > paper.clientWidth, fontError: [...document.fonts].some(font => font.status === "error") };
  });
  expect(rendering.height).toBeGreaterThan(100);
  expect(rendering).toMatchObject({ aligned: true, overflow: false, fontError: false });
  await page.locator("#direct-print-fixture").evaluate(frame => frame.remove());
  await page.evaluate(() => {
    window.Capacitor.getPlatform = () => "web";
    window.Capacitor.isNativePlatform = () => false;
  });
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.locator('#receipt-dialog [data-close]').click();
  await page.locator("#last-receipt").click();
  expect(await receipt.innerHTML()).toBe(saved);
  await expect(page.locator("#print-service-receipt")).toBeHidden();
  await expect(page.locator("#printer-setup")).toBeHidden();
  await page.locator('#receipt-dialog [data-close]').click();
  await page.locator('[data-product-id="menu-001"]').click();
  await page.locator("#pay-button").click();
  await page.locator("#complete-sale").click();
  await expect(receipt.locator(".receipt-meta")).toContainText("AR/2627/000002");
});
