import { dayAt } from "./domain.js";

/** Calendar arithmetic stays independent of the host timezone and DST. Weeks start Monday. */
export function datePreset(preset, today = dayAt()) {
  const date = new Date(`${today}T00:00:00Z`);
  if (
    !Number.isFinite(date.getTime()) ||
    date.toISOString().slice(0, 10) !== today
  )
    throw new Error("Invalid report day");
  let from = today,
    to = today;
  if (preset === "yesterday") {
    date.setUTCDate(date.getUTCDate() - 1);
    from = to = date.toISOString().slice(0, 10);
  } else if (preset === "week") {
    date.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
    from = date.toISOString().slice(0, 10);
  } else if (preset === "month") from = today.slice(0, 8) + "01";
  else if (preset !== "today") throw new Error("Unknown date preset");
  return { from, to };
}
