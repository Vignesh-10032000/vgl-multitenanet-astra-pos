import { chromium } from "@playwright/test";
import { preview } from "vite";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { unlockFixture } from "../tests/restaurant-browser/access-helper.js";

const label = process.argv[2] || "current";
if (!/^[a-z0-9-]+$/.test(label)) throw new Error("Invalid profile label");
const output = resolve("test-results/startup-polish");
await mkdir(output, { recursive: true });
const server = await preview({ configFile: resolve("restaurant/vite.config.js"), preview: { host: "127.0.0.1", port: 5176, strictPort: true } });
const browser = await chromium.launch();
try {
  const samples = [];
  for (let index = 0; index < 5; index++) {
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.goto("http://127.0.0.1:5176/?startupProfile=1");
    const read = async kind => {
      await page.waitForFunction(() => performance.getEntriesByName("restaurant:login-first-paint").length && performance.getEntriesByName("restaurant:ready").length);
      return { kind, marks: await page.evaluate(() => Object.fromEntries(performance.getEntriesByType("mark").map(mark => [mark.name.replace("restaurant:", ""), Math.round(mark.startTime * 10) / 10]))) };
    };
    samples.push(await read("fresh-browser-storage"));
    await unlockFixture(page);
    await page.locator("#lock-workspace").click();
    await page.reload();
    samples.push(await read("relaunch-owner-locked"));
    if (errors.length) throw new Error(errors.join("; "));
    await context.close();
  }
  const result = { label, scope: "Desktop Chromium / production Vite web build / sql.js browser preview. NOT an Android debug/release or TVS measurement. Five independent empty browser contexts and five locked-owner relaunches; no shared backup folder.", browser: browser.version(), samples };
  await writeFile(resolve(output, `${label}.json`), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
} finally {
  await browser.close();
  await new Promise(resolve => server.httpServer.close(resolve));
}
