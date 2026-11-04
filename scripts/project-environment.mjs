import { existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

// Loaded before project CLIs so their browser profiles and temporary files stay on D:.
const root = fileURLToPath(new URL("../", import.meta.url));
const tools = resolve(root, ".tools");
const temp = resolve(tools, "tmp");
mkdirSync(temp, { recursive: true });
for (const key of ["TEMP", "TMP", "TMPDIR"]) process.env[key] = temp;
process.env.GRADLE_USER_HOME = resolve(tools, "gradle");
process.env.UV_CACHE_DIR = resolve(tools, "uv-cache");
process.env.npm_config_cache = resolve(tools, "npm-cache");
if (existsSync(resolve(tools, "playwright")))
  process.env.PLAYWRIGHT_BROWSERS_PATH = resolve(tools, "playwright");
if (existsSync(resolve(tools, "android-sdk"))) {
  process.env.ANDROID_HOME = resolve(tools, "android-sdk");
  process.env.ANDROID_SDK_ROOT = process.env.ANDROID_HOME;
}
if (existsSync(resolve(tools, "android-user")))
  process.env.ANDROID_USER_HOME = resolve(tools, "android-user");
