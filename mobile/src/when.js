const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function pad(value) {
  return String(value).padStart(2, "0");
}

function monthCells(year, month) {
  const leading = new Date(year, month, 1).getDay();
  const count = new Date(year, month + 1, 0).getDate();
  const cells = Array(leading).fill(null);
  for (let day = 1; day <= count; day += 1) {
    cells.push(day);
  }
  while (cells.length % 7 !== 0) {
    cells.push(null);
  }
  return cells;
}

function monthTitle(year, month) {
  return `${MONTHS[month]} ${year}`;
}

function formatWhen(parts) {
  return `${parts.year}-${pad(parts.month + 1)}-${pad(parts.day)} ${pad(parts.hour)}:${pad(parts.minute)}`;
}

function readWhen(value, now) {
  const matched = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(String(value || "").trim());
  const clock = now || new Date();
  if (!matched) {
    return {
      year: clock.getFullYear(),
      month: clock.getMonth(),
      day: clock.getDate(),
      hour: 9,
      minute: 0,
    };
  }
  return {
    year: Number(matched[1]),
    month: Number(matched[2]) - 1,
    day: Number(matched[3]),
    hour: matched[4] === undefined ? 0 : Number(matched[4]),
    minute: matched[5] === undefined ? 0 : Number(matched[5]),
  };
}

function shiftMonth(year, month, delta) {
  const next = new Date(year, month + delta, 1);
  return { year: next.getFullYear(), month: next.getMonth() };
}

function wrapUnit(value, max) {
  if (value < 0) {
    return max;
  }
  if (value > max) {
    return 0;
  }
  return value;
}

module.exports = {
  MONTHS,
  WEEKDAYS,
  formatWhen,
  monthCells,
  monthTitle,
  readWhen,
  shiftMonth,
  wrapUnit,
};
