import { defineConfig } from "vite";
import { resolve } from "node:path";

const sourceRoot = resolve(import.meta.dirname, "src/vglpos/web/static/src");

export default defineConfig({
  root: sourceRoot,
  base: "/static/dist/",
  build: {
    outDir: resolve(import.meta.dirname, "src/vglpos/web/static/dist"),
    emptyOutDir: true,
    cssCodeSplit: false,
    manifest: "manifest.json",
    rollupOptions: {
      input: {
        app: resolve(sourceRoot, "js/app.js"),
        login: resolve(sourceRoot, "js/login.js"),
        pos: resolve(sourceRoot, "js/pos.js"),
        dashboard: resolve(sourceRoot, "js/dashboard.js"),
        products: resolve(sourceRoot, "js/products.js"),
        customers: resolve(sourceRoot, "js/customers.js"),
        sales: resolve(sourceRoot, "js/sales.js"),
        reports: resolve(sourceRoot, "js/reports.js"),
        settings: resolve(sourceRoot, "js/settings.js"),
        receipt: resolve(sourceRoot, "js/receipt.js")
      },
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]"
      }
    }
  }
});
