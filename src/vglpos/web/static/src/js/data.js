export function localDateIso(date = new Date()) {
  const year = String(date.getFullYear()).padStart(4, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function utcTimestamp(value) {
  // SQLite returns UTC audit timestamps without an offset; preserve their UTC meaning.
  const timestamp = String(value);
  return /(?:Z|[+-]\d{2}:\d{2})$/i.test(timestamp) ? timestamp : `${timestamp}Z`;
}

export function scaledInteger(value, scale = 2) {
  const match = String(value ?? "0").trim().match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) return 0n;
  const factor = 10n ** BigInt(scale);
  const fraction = (match[3] || "").padEnd(scale, "0").slice(0, scale);
  const amount = BigInt(match[2]) * factor + BigInt(fraction || "0");
  return match[1] === "-" ? -amount : amount;
}

export function decimalCompare(left, right, scale = 3) {
  const difference = scaledInteger(left, scale) - scaledInteger(right, scale);
  return difference < 0n ? -1 : difference > 0n ? 1 : 0;
}

export function downloadJson(filename, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
