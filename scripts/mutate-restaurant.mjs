import { readFile, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

// Deliberately small semantic mutation audit; this is not a Stryker coverage score.
// Never rewrites the working source. Each variant is loaded from a temporary file.
const source = await readFile("restaurant/domain.js", "utf8");
const variants = [
  ["tax-added-instead-of-included", "10000 + rate)", "10000)"],
  ["discount-sign", "const net = gross - discount;", "const net = gross + discount;"],
  ["lost-cgst-paise", "Math.floor(line.tax_paise / 2)", "Math.ceil(line.tax_paise / 2)"],
  ["change-sign", "change_paise: tendered - total", "change_paise: total - tendered"],
  ["accept-unreconciled-split", "result.reduce((sum, row) => sum + row.amount_paise, 0) !== total", "false"],
  ["round-down-instead-of-half-up", "BigInt(n) * 2n + BigInt(d)", "BigInt(n) * 2n"],
];
const output = resolve("test-results/reliability-audit/mutations");
await mkdir(output, { recursive: true });
const directory = await mkdtemp(join(tmpdir(), "pos-mutation-"));
const results = [];
try {
  for (const [name, original, replacement] of [["control", "", ""], ...variants]) {
    if (name !== "control" && source.split(original).length !== 2) throw new Error(`Ambiguous mutation: ${name}`);
    const path = join(directory, `${name}.mjs`);
    await writeFile(path, name === "control" ? source : source.replace(original, replacement));
    const result = spawnSync(process.execPath, ["--import", "./scripts/project-environment.mjs", "--test", "tests/restaurant/financial-properties.test.js"], {
      cwd: process.cwd(), encoding: "utf8", timeout: 30000,
      env: { ...process.env, RESTAURANT_DOMAIN_UNDER_TEST: pathToFileURL(path).href },
    });
    await writeFile(join(output, `${name}.log`), `${result.stdout || ""}\n${result.stderr || ""}`);
    if (result.error) throw result.error;
    const detected = result.status !== 0 && /AssertionError/.test(result.stdout + result.stderr);
    if (name === "control" && result.status !== 0) throw new Error("Unmutated control failed");
    results.push({ name, exit_code: result.status, detected });
  }
} finally { await rm(directory, { recursive: true, force: true }); }
const killed = results.slice(1).filter((r) => r.detected).length;
const report = { method: "Six explicit financial semantic mutations with an unmutated control; not an exhaustive StrykerJS score", killed, total: variants.length, score_percent: killed * 100 / variants.length, results };
await writeFile(join(output, "results.json"), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
if (killed !== variants.length) process.exitCode = 1;
