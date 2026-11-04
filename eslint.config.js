import js from "@eslint/js";
import globals from "globals";

const browserFiles = [
  "restaurant/*.js",
  "src/vglpos/web/static/src/js/{pos,dashboard,payment-view,payment-display,pos-icons,i18n,ui,data}.js",
];

export default [
  {
    ignores: [
      "node_modules/**",
      "dist/**",
      "android/**",
      ".tools/**",
      "artifacts/**",
      "test-results/**",
    ],
  },
  {
    ...js.configs.recommended,
    files: [
      ...browserFiles,
      "tests/restaurant/**/*.js",
      "tests/restaurant-browser/**/*.js",
      "scripts/*.mjs",
      "eslint.config.js",
    ],
  },
  {
    files: browserFiles,
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: globals.browser,
    },
    rules: {
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
    },
  },
  {
    files: [
      "restaurant/{vite.config,playwright.config,original-billing-template}.js",
      "tests/**/*.js",
      "scripts/*.mjs",
      "eslint.config.js",
    ],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
];
