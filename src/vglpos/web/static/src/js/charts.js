import { scaledInteger } from "./data.js";
import { formatDate, formatMoney } from "./i18n.js";
import { clearChildren } from "./ui.js";

export function renderRevenueBars(container, points) {
  clearChildren(container);
  const amounts = points.map((point) => scaledInteger(point.net_amount, 2));
  const maximum = amounts.reduce((largest, amount) => (amount > largest ? amount : largest), 0n);
  points.forEach((point, index) => {
    const column = document.createElement("div");
    column.className = "bar-column";
    const track = document.createElement("div");
    track.className = "bar-track";
    const value = document.createElement("span");
    value.className = "bar-value";
    value.textContent = formatMoney(point.net_amount);
    const fill = document.createElement("div");
    fill.className = "bar-fill";
    const level = maximum > 0n ? (amounts[index] * 10n) / maximum : 0n;
    fill.classList.add(`bar-height-${level}`);
    const label = document.createElement("span");
    label.className = "bar-label";
    label.textContent = formatDate(`${point.business_date}T00:00:00`, { weekday: "short" });
    track.append(value, fill);
    column.append(track, label);
    container.append(column);
  });
}
