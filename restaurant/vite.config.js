import { defineConfig } from "vite";
import { resolve } from "node:path";
import { originalBillingTemplate } from "./original-billing-template.js";

export default defineConfig({
  root: resolve(import.meta.dirname),
  base: "./",
  plugins: [originalBillingTemplate()],
  publicDir: "public",
  server: { host: "127.0.0.1", port: 5174, strictPort: true },
  build: {
    outDir: resolve(import.meta.dirname, "../dist/restaurant"),
    emptyOutDir: true,
    target: "es2020",
  },
});
