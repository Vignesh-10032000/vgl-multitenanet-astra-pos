import test from "node:test";
import assert from "node:assert/strict";
import { utcTimestamp } from "../../src/vglpos/web/static/src/js/data.js";

test("RECEIPT-02 UTC timestamps without offsets retain the correct store time", () => {
  const format = new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
  assert.equal(format.format(new Date(utcTimestamp("2026-10-16T16:21:00"))), "21:51");
  assert.equal(format.format(new Date(utcTimestamp("2026-10-16T16:21:00Z"))), "21:51");
  assert.equal(format.format(new Date(utcTimestamp("2026-10-16T21:51:00+05:30"))), "21:51");
});
