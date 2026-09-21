import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { computeTax } from "../../src/vglpos/web/static/src/js/tax-engine.js";

const fixture = new URL("../fixtures/tax_parity_200.json", import.meta.url);

test("offline tax engine matches Python over all 200 shared scenarios", async () => {
  const payload = JSON.parse(await readFile(fixture, "utf8"));
  assert.equal(payload.verification.scenario_count, 200);
  assert.equal(payload.scenarios.length, 200);
  for (const scenario of payload.scenarios) {
    assert.deepEqual(computeTax(scenario.input), scenario.expected, scenario.id);
  }
});
