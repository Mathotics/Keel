const { statusLabel } = require("./work");
const {
  NEEDS_CONNECTION,
  addDays,
  monthStart,
  monthEnd,
  shiftMonth,
  weekdayIndex,
  savedIssues,
  onlineIssues,
  enabledProjects,
  calendarDay,
} = require("./calendar");

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
const SHORT = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const DOW = ["M", "T", "W", "T", "F", "S", "S"];
const TYPE_COLOR = {
  epic: "#0068B0",
  story: "#0F7A73",
  subtask: "#B45309",
};
const LEGEND = "A solid arrow means blocks. A dashed line means relates to.";

function parseScale(value) {
  return value === "quarter" || value === "year" ? value : "month";
}

function parseDay(value, today) {
  return calendarDay(value) || today;
}

function quarterStart(iso) {
  const [year, month] = monthStart(iso).split("-").map(Number);
  const first = Math.floor((month - 1) / 3) * 3 + 1;
  return `${String(year).padStart(4, "0")}-${String(first).padStart(2, "0")}-01`;
}

function yearStart(iso) {
  return `${iso.slice(0, 4)}-01-01`;
}

function anchorFor(scale, focus, today) {
  const day = parseDay(focus, today);
  if (scale === "quarter") {
    return quarterStart(day);
  }
  if (scale === "year") {
    return yearStart(day);
  }
  return monthStart(day);
}

function bounds(anchor, scale) {
  if (scale === "year") {
    return [`${anchor.slice(0, 4)}-01-01`, `${anchor.slice(0, 4)}-12-31`];
  }
  if (scale === "quarter") {
    const start = quarterStart(anchor);
    return [start, monthEnd(shiftMonth(start, 2))];
  }
  const start = monthStart(anchor);
  return [start, monthEnd(start)];
}

function columnStarts(scale, start, end) {
  if (scale === "year") {
    const year = start.slice(0, 4);
    return Array.from({ length: 12 }, (_, index) => (
      `${year}-${String(index + 1).padStart(2, "0")}-01`
    ));
  }
  if (scale === "quarter") {
    const weeks = [];
    let cursor = addDays(start, -weekdayIndex(start));
    const last = addDays(end, -weekdayIndex(end));
    while (cursor <= last) {
      weeks.push(cursor);
      cursor = addDays(cursor, 7);
    }
    return weeks;
  }
  const days = [];
  let cursor = start;
  while (cursor <= end) {
    days.push(cursor);
    cursor = addDays(cursor, 1);
  }
  return days;
}

function slotOf(day, starts) {
  let slot = 0;
  for (let index = 0; index < starts.length; index += 1) {
    if (starts[index] <= day) {
      slot = index;
    } else {
      break;
    }
  }
  return slot;
}

function spanOf(issue) {
  const start = calendarDay(issue.start_at);
  const due = calendarDay(issue.due_at);
  if (!start && !due) {
    return null;
  }
  if (!start) {
    return { start: due, end: due };
  }
  if (!due) {
    return { start, end: start };
  }
  return { start, end: due };
}

function sortKey(issue, span) {
  return [span.start, span.end, issue.projectKey || "", issue.number || 0];
}

function comparePlaced(left, right) {
  const [leftStart, leftEnd, leftKey, leftNumber] = left.sort;
  const [rightStart, rightEnd, rightKey, rightNumber] = right.sort;
  if (leftStart !== rightStart) {
    return leftStart < rightStart ? -1 : 1;
  }
  if (leftEnd !== rightEnd) {
    return leftEnd < rightEnd ? -1 : 1;
  }
  if (leftKey !== rightKey) {
    return leftKey < rightKey ? -1 : 1;
  }
  return leftNumber - rightNumber;
}

function arrange(items) {
  const byId = new Map(items.map((item) => [item.id, item]));
  const children = new Map();
  for (const item of items) {
    const parent = item.parentId != null && byId.has(item.parentId) ? item.parentId : null;
    const group = children.get(parent) || [];
    group.push(item);
    children.set(parent, group);
  }
  for (const group of children.values()) {
    group.sort(comparePlaced);
  }
  const ordered = [];
  const seen = new Set();
  function walk(parent, depth) {
    for (const item of children.get(parent) || []) {
      if (seen.has(item.id)) {
        continue;
      }
      seen.add(item.id);
      ordered.push({ ...item, depth });
      walk(item.id, depth + 1);
    }
  }
  walk(null, 0);
  for (const item of items) {
    if (!seen.has(item.id)) {
      ordered.push({ ...item, depth: 0 });
    }
  }
  return ordered;
}

function columnOf(scale, start, isToday) {
  const [year, month, day] = start.split("-").map(Number);
  if (scale === "year") {
    return {
      mark: SHORT[month - 1],
      dow: "",
      hint: `${MONTHS[month - 1]} ${year}`,
      isToday,
    };
  }
  if (scale === "quarter") {
    return {
      mark: `${SHORT[month - 1]} ${day}`,
      dow: "",
      hint: `Week of ${MONTHS[month - 1]} ${day}, ${year}`,
      isToday,
    };
  }
  const weekday = weekdayIndex(start);
  return {
    mark: String(day),
    dow: DOW[weekday],
    hint: `${WEEKDAYS[weekday]}, ${MONTHS[month - 1]} ${day}, ${year}`,
    isToday,
  };
}

function labelFor(scale, anchor, start, end) {
  if (scale === "year") {
    return anchor.slice(0, 4);
  }
  if (scale === "quarter") {
    const [startYear, startMonth] = start.split("-").map(Number);
    const [, endMonth] = end.split("-").map(Number);
    return `${MONTHS[startMonth - 1]}\u2013${MONTHS[endMonth - 1]} ${startYear}`;
  }
  const [year, month] = anchor.split("-").map(Number);
  return `${MONTHS[month - 1]} ${year}`;
}

function emptyNote(scale) {
  if (scale === "year") {
    return "Nothing dated falls in this year.";
  }
  if (scale === "quarter") {
    return "Nothing dated falls in this quarter.";
  }
  return "Nothing dated falls in this month.";
}

function num(value) {
  const text = value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  return text === "" || text === "-" ? "0" : text;
}

function samePoint(left, right) {
  return Math.abs(left[0] - right[0]) <= 0.001 && Math.abs(left[1] - right[1]) <= 0.001;
}

function dedupe(points) {
  const kept = [];
  for (const point of points) {
    if (!kept.length || !samePoint(kept[kept.length - 1], point)) {
      kept.push(point);
    }
  }
  return kept;
}

function pathOf(points) {
  return points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${num(point[0])} ${num(point[1])}`)
    .join(" ");
}

function anchorX(item, which, scale) {
  const left = item.column - 1;
  const point = scale === "month" && item.start === item.end;
  if (which === "finish") {
    return point ? left + 0.5 : left + item.length;
  }
  if (which === "start") {
    return point ? left + 0.5 : left;
  }
  return point ? left + 0.5 : left + item.length / 2;
}

function blocksPoints(x1, y1, x2, y2, columns, rows) {
  const stub = 0.45;
  if (x2 >= x1 + stub) {
    return dedupe([[x1, y1], [x1 + stub, y1], [x1 + stub, y2], [x2, y2]]);
  }
  const leave = Math.min(columns, x1 + stub);
  const toward = y2 >= y1 ? 0.82 : -0.82;
  const lane = Math.min(Math.max(y1 + toward, 0.12), Math.max(rows - 0.12, 0.12));
  const approach = x2 >= stub ? x2 - stub : Math.min(columns, x2 + stub);
  return dedupe([
    [x1, y1],
    [leave, y1],
    [leave, lane],
    [approach, lane],
    [approach, y2],
    [x2, y2],
  ]);
}

function relatesPoints(x1, y1, x2, y2) {
  const lane = y1 + (y2 >= y1 ? 0.42 : -0.42);
  return dedupe([[x1, y1], [x1, lane], [x2, lane], [x2, y2]]);
}

function tipDirection(points) {
  const [x1, y1] = points[points.length - 2];
  const [x2, y2] = points[points.length - 1];
  if (Math.abs(x2 - x1) >= Math.abs(y2 - y1)) {
    return x2 >= x1 ? "right" : "left";
  }
  return y2 >= y1 ? "down" : "up";
}

function segmentsOf(points) {
  const segments = [];
  for (let index = 1; index < points.length; index += 1) {
    const [x1, y1] = points[index - 1];
    const [x2, y2] = points[index];
    if (Math.abs(x2 - x1) >= Math.abs(y2 - y1)) {
      segments.push({ axis: "x", x: Math.min(x1, x2), y: y1, length: Math.abs(x2 - x1) });
    } else {
      segments.push({ axis: "y", x: x1, y: Math.min(y1, y2), length: Math.abs(y2 - y1) });
    }
  }
  return segments.filter((segment) => segment.length > 0.001);
}

function linksFor(rows, edges, scale, columns) {
  if (rows.length < 2) {
    return [];
  }
  const byId = new Map(rows.map((row) => [row.id, row]));
  const order = new Map(rows.map((row, index) => [row.id, index]));
  const links = [];
  for (const edge of edges || []) {
    const source = byId.get(edge.source_id);
    const target = byId.get(edge.target_id);
    if (!source || !target || source.id === target.id) {
      continue;
    }
    const y1 = order.get(source.id) + 0.5;
    const y2 = order.get(target.id) + 0.5;
    const blocks = edge.kind === "blocks";
    const points = blocks
      ? blocksPoints(
        anchorX(source, "finish", scale),
        y1,
        anchorX(target, "start", scale),
        y2,
        columns,
        rows.length,
      )
      : relatesPoints(
        anchorX(source, "center", scale),
        y1,
        anchorX(target, "center", scale),
        y2,
      );
    if (points.length < 2) {
      continue;
    }
    const end = points[points.length - 1];
    links.push({
      kind: blocks ? "blocks" : "relates_to",
      text: blocks ? `${source.key} blocks ${target.key}` : `${source.key} relates to ${target.key}`,
      path: pathOf(points),
      tip: blocks ? tipDirection(points) : "",
      tipX: end[0],
      tipY: end[1],
      segments: segmentsOf(points),
    });
  }
  links.sort((left, right) => {
    const kind = (left.kind === "blocks" ? 0 : 1) - (right.kind === "blocks" ? 0 : 1);
    return kind || (left.text < right.text ? -1 : left.text > right.text ? 1 : 0);
  });
  return links;
}

function placedRows(issues, scale, windowStart, windowEnd, starts) {
  const items = [];
  for (const issue of issues) {
    const span = spanOf(issue);
    if (!span || span.end < windowStart || span.start > windowEnd) {
      continue;
    }
    const shownStart = span.start < windowStart ? windowStart : span.start;
    const shownEnd = span.end > windowEnd ? windowEnd : span.end;
    const first = slotOf(shownStart, starts);
    const last = slotOf(shownEnd, starts);
    items.push({
      id: issue.id,
      key: issue.key,
      title: issue.title,
      type: issue.type,
      status: issue.status,
      statusLabel: statusLabel(issue.status),
      color: TYPE_COLOR[issue.type] || TYPE_COLOR.story,
      parentId: issue.parentId,
      pending: issue.pending,
      start: span.start,
      end: span.end,
      sort: sortKey(issue, span),
      column: first + 1,
      length: last - first + 1,
      continuesBefore: span.start < windowStart,
      continuesAfter: span.end > windowEnd,
      point: scale === "month" && span.start === span.end,
    });
  }
  return arrange(items);
}

function ganttView({
  library,
  remote,
  links = [],
  view,
  focus,
  today,
  projectId = null,
  userId,
  filter,
}) {
  const scale = parseScale(view);
  const shownToday = parseDay(today, "1970-01-01");
  const anchor = anchorFor(scale, focus, shownToday);
  const [windowStart, windowEnd] = bounds(anchor, scale);
  const starts = columnStarts(scale, windowStart, windowEnd);
  const online = Array.isArray(remote);
  const issues = online
    ? onlineIssues(library, remote, projectId, userId, filter)
    : savedIssues(library, projectId, userId, filter);
  const rows = placedRows(issues, scale, windowStart, windowEnd, starts);
  const todayColumn = shownToday >= windowStart && shownToday <= windowEnd
    ? slotOf(shownToday, starts) + 1
    : null;
  const drawn = linksFor(rows, links, scale, starts.length);
  return {
    label: labelFor(scale, anchor, windowStart, windowEnd),
    view: scale,
    focus: anchor,
    banner: online ? "" : NEEDS_CONNECTION,
    empty: rows.length ? "" : emptyNote(scale),
    legend: drawn.length ? LEGEND : "",
    columns: starts.map((start, index) => columnOf(scale, start, index + 1 === todayColumn)),
    rows,
    links: drawn,
    todayColumn,
    projects: enabledProjects(library).map((project) => ({ id: project.id, key: project.key })),
  };
}

function moveFocus(view, focus, today, direction) {
  const scale = parseScale(view);
  const shownToday = parseDay(today, "1970-01-01");
  const anchor = anchorFor(scale, focus, shownToday);
  if (direction === "today") {
    return anchorFor(scale, shownToday, shownToday);
  }
  const step = scale === "year" ? 12 : scale === "quarter" ? 3 : 1;
  return anchorFor(scale, shiftMonth(anchor, step * direction), shownToday);
}

function focusForView(nextView, currentView, focus, today) {
  const next = parseScale(nextView);
  const current = parseScale(currentView);
  const shownToday = parseDay(today, "1970-01-01");
  const anchor = anchorFor(current, focus, shownToday);
  if (next === current) {
    return anchor;
  }
  const [start, end] = bounds(anchor, current);
  const inside = shownToday >= start && shownToday <= end ? shownToday : start;
  return anchorFor(next, inside, shownToday);
}

module.exports = {
  LEGEND,
  ganttView,
  focusForView,
  moveFocus,
};
