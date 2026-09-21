import assert from "node:assert/strict";
import test from "node:test";

import { decimalCompare, localDateIso, scaledInteger } from "../../src/vglpos/web/static/src/js/data.js";

test("scaledInteger preserves paise and three-decimal quantities without floats", () => {
  assert.equal(scaledInteger("1,00,000.99"), 0n);
  assert.equal(scaledInteger("100000.99"), 10000099n);
  assert.equal(scaledInteger("0.125", 3), 125n);
  assert.equal(scaledInteger("-1.50"), -150n);
});

test("decimalCompare compares normalized quantity strings exactly", () => {
  assert.equal(decimalCompare("0.100", "0.099"), 1);
  assert.equal(decimalCompare("12.340", "12.34"), 0);
  assert.equal(decimalCompare("999.999", "1000.000"), -1);
});

test("localDateIso uses local calendar fields instead of UTC conversion", () => {
  assert.equal(localDateIso(new Date(2026, 8, 20, 23, 59)), "2026-09-20");
});
