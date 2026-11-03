import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "../tests/restaurant-browser",
  outputDir: "../test-results/restaurant-browser",
  workers: 1,
  fullyParallel: false,
  timeout: 45000,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5175",
    viewport: { width: 1920, height: 1080 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: {
    command:
      "npx vite preview --config restaurant/vite.config.js --host 127.0.0.1 --port 5175 --strictPort",
    cwd: "..",
    url: "http://127.0.0.1:5175",
    reuseExistingServer: false,
  },
});
