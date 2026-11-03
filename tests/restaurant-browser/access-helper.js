/** Disposable browser fixtures only; never configures the user's localhost profile. */
export async function unlockFixture(page) {
  await page.waitForFunction(
    () =>
      document.body.dataset.locked === "false" ||
      !document.querySelector("#access-form").hidden,
  );
  // The shell now paints before DB readiness; wait until setup vs login is known.
  await page.waitForFunction(() => document.body.dataset.locked === "false" || !document.querySelector("#access-submit").disabled);
  if (await page.locator("#access-screen").isVisible()) {
    await page.locator("#access-username").fill("test-owner");
    await page.locator("#access-password").fill("Fixture-only-owner-482!");
    if (await page.locator("#access-confirm-row").isVisible())
      await page.locator("#access-confirm").fill("Fixture-only-owner-482!");
    await page.locator("#access-submit").click();
    await page.locator("#access-screen").waitFor({ state: "hidden" });
  }
}

/** Existing monetary regressions explicitly exercise their original inclusive setup. */
export async function unlockInclusiveFixture(page) {
  await unlockFixture(page);
  const previous = new URL(page.url()).hash || "#billing";
  await page.locator('[data-nav="settings"]').click();
  const basis = page.locator('#settings-form [name="tax_inclusive"]');
  await basis.waitFor({ state: "visible" });
  if (await basis.inputValue() !== "true") {
    await basis.selectOption("true");
    await page.locator('#settings-form button.button-primary').click();
    await page.getByText("Setup saved locally", { exact: true }).waitFor();
  }
  await page.locator(`[data-nav="${previous.slice(1)}"]`).click();
}
