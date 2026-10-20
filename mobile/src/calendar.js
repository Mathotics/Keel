const { matchesIssue } = require("./filters");
const { statusLabel } = require("./work");

const NEEDS_CONNECTION = "Showing the saved copy.";
const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
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
const TYPE_COLOR = {
  epic: "#0068B0",
  story: "#0F7A73",
  subtask: "#B45309",
};

function addDays(iso, days) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function monthStart(iso) {
  return `${iso.slice(0, 7)}-01`;
}

function monthEnd(iso) {
  const [year, month] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month, 0));
  return date.toISOString().slice(0, 10);
}

function shiftMonth(iso, delta) {
  const [year, month] = monthStart(iso).split("-").map(Number);
  const index = year * 12 + (month - 1) + delta;
  let nextYear = Math.floor(index / 12);
  let nextMonth = index % 12;
  if (nextMonth < 0) {
    nextMonth += 12;
    nextYear -= 1;
  }
  if (nextYear < 1) {
    return "0001-01-01";
  }
  if (nextYear > 9999) {
    return "9999-12-01";
  }
  return `${String(nextYear).padStart(4, "0")}-${String(nextMonth + 1).padStart(2, "0")}-01`;
}

function weekdayIndex(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return (date.getUTCDay() + 6) % 7;
}

function mondayOf(iso) {
  return addDays(iso, -weekdayIndex(iso));
}

function calendarDay(value) {
  const matched = /^(\d{4}-\d{2}-\d{2})/.exec(String(value || ""));
  return matched ? matched[1] : null;
}

function parseDay(value, today) {
  return calendarDay(value) || today;
}

function parseView(value) {
  return value === "week" || value === "day" ? value : "month";
}

function parseMode(value) {
  return value === "completed" || value === "created" ? value : "start";
}

function enabledProjects(library) {
  return Object.values((library && library.projects) || {})
    .filter((project) => project && project.enabled)
    .sort((left, right) => (left.key || "").localeCompare(right.key || ""));
}

function issueNumber(issue) {
  if (Number.isInteger(issue.number)) {
    return issue.number;
  }
  const matched = /-(\d+)$/.exec(issue.key || "");
  return matched ? Number(matched[1]) : 0;
}

function utcMinutes(value) {
  const text = String(value || "");
  if (!text) {
    return 0;
  }
  if (!/Z$|[+-]\d\d:?\d\d$/.test(text)) {
    const matched = /T(\d{2}):(\d{2})/.exec(text);
    return matched ? Number(matched[1]) * 60 + Number(matched[2]) : 0;
  }
  const parsed = Date.parse(text);
  if (Number.isNaN(parsed)) {
    return 0;
  }
  const date = new Date(parsed);
  return date.getUTCHours() * 60 + date.getUTCMinutes();
}

function localParts(value, offsetMinutes) {
  if (!value) {
    return null;
  }
  const text = String(value);
  const utc = /Z$|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`;
  const parsed = Date.parse(utc);
  if (Number.isNaN(parsed)) {
    const day = calendarDay(value);
    return day ? { day, minutes: utcMinutes(value) } : null;
  }
  const local = new Date(parsed - offsetMinutes * 60 * 1000);
  return {
    day: local.toISOString().slice(0, 10),
    minutes: local.getUTCHours() * 60 + local.getUTCMinutes(),
  };
}

function formatClock(minutes) {
  const hour = Math.floor(minutes / 60) % 24;
  const minute = minutes % 60;
  const suffix = hour < 12 ? "AM" : "PM";
  const shown = hour % 12 || 12;
  if (!minute) {
    return `${shown} ${suffix}`;
  }
  return `${shown}:${String(minute).padStart(2, "0")} ${suffix}`;
}

function decorate(raw, project, pending) {
  return {
    id: raw.id,
    key: raw.key || "",
    number: issueNumber(raw),
    title: raw.title || "",
    type: raw.type || "story",
    status: raw.status,
    projectKey: (project && project.key) || raw.projectKey || "",
    assigneeId: raw.assignee_id,
    start_at: raw.start_at,
    due_at: raw.due_at,
    created_at: raw.created_at,
    pending: Boolean(pending),
  };
}

function inScope(raw, projectId, userId) {
  if (projectId == null) {
    return Number(raw.assignee_id) === Number(userId);
  }
  return true;
}

function savedIssues(library, projectId, userId, filter) {
  const rows = [];
  for (const project of enabledProjects(library)) {
    if (projectId != null && project.id !== projectId) {
      continue;
    }
    for (const record of Object.values(project.issues || {})) {
      const raw = record.raw || {};
      if (!inScope(raw, projectId, userId)) {
        continue;
      }
      if (!matchesIssue(raw, filter, { projectId: project.id, ignoreProject: projectId != null })) {
        continue;
      }
      rows.push(decorate(raw, project, record.pending || record.conflict));
    }
  }
  return rows;
}

function onlineIssues(library, remote, projectId, userId, filter) {
  const byId = new Map();
  const projects = (library && library.projects) || {};
  for (const raw of remote || []) {
    const project = projects[raw.project_id] || { key: raw.projectKey || "", enabled: true };
    if (project.enabled === false || !inScope(raw, projectId, userId)) {
      continue;
    }
    if (!matchesIssue(raw, filter, { projectId: raw.project_id || project.id, ignoreProject: projectId != null })) {
      continue;
    }
    if (projectId != null && raw.project_id !== projectId && project.id !== projectId) {
      continue;
    }
    byId.set(raw.id, decorate(raw, project, false));
  }
  for (const project of enabledProjects(library)) {
    if (projectId != null && project.id !== projectId) {
      continue;
    }
    for (const record of Object.values(project.issues || {})) {
      const raw = record.raw || {};
      const local = record.pending || record.conflict || raw.id < 0;
      if (!local || !inScope(raw, projectId, userId)) {
        continue;
      }
      if (!matchesIssue(raw, filter, { projectId: project.id, ignoreProject: projectId != null })) {
        continue;
      }
      byId.set(raw.id, decorate(raw, project, true));
    }
  }
  return [...byId.values()];
}

function windowOf(issue) {
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

function placed(issue, mode, completedAt, offsetMinutes) {
  if (mode === "completed") {
    if (issue.status !== "done") {
      return null;
    }
    const moment = completedAt ? completedAt[issue.id] : null;
    if (!moment) {
      return null;
    }
    const parts = localParts(moment, offsetMinutes);
    if (!parts) {
      return null;
    }
    return { start: parts.day, end: parts.day, startMinute: parts.minutes, endMinute: parts.minutes, point: true };
  }
  if (mode === "created") {
    const parts = localParts(issue.created_at, offsetMinutes);
    if (!parts) {
      return null;
    }
    return { start: parts.day, end: parts.day, startMinute: parts.minutes, endMinute: parts.minutes, point: true };
  }
  const span = windowOf(issue);
  if (!span) {
    return null;
  }
  const point = !issue.start_at || !issue.due_at || String(issue.start_at) === String(issue.due_at);
  const startMinute = issue.start_at ? utcMinutes(issue.start_at) : utcMinutes(issue.due_at);
  const endMinute = issue.due_at ? utcMinutes(issue.due_at) : startMinute;
  return { ...span, startMinute, endMinute, point };
}

function overlaps(bar, start, end) {
  return bar.end >= start && bar.start <= end;
}

function compareBars(left, right) {
  const start = left.bar.start.localeCompare(right.bar.start);
  if (start) {
    return start;
  }
  const project = left.issue.projectKey.localeCompare(right.issue.projectKey);
  return project || left.issue.number - right.issue.number;
}

function timeLabel(bar, day) {
  if (bar.point || bar.start === bar.end) {
    if (bar.point) {
      return formatClock(bar.startMinute);
    }
    return `${formatClock(bar.startMinute)} – ${formatClock(bar.endMinute)}`;
  }
  if (day === bar.start) {
    return `From ${formatClock(bar.startMinute)}`;
  }
  if (day === bar.end) {
    return `Until ${formatClock(bar.endMinute)}`;
  }
  return "All day";
}

function chip(issue, bar, day, withTime) {
  return {
    id: issue.id,
    key: issue.key,
    title: issue.title,
    status: issue.status,
    statusLabel: statusLabel(issue.status),
    type: issue.type,
    color: TYPE_COLOR[issue.type] || TYPE_COLOR.story,
    pending: issue.pending,
    time: withTime ? timeLabel(bar, day) : "",
  };
}

function emptyNote(mode, period) {
  if (mode === "start") {
    if (period === "day") {
      return "Nothing dated falls on this day.";
    }
    return `Nothing dated falls in this ${period}.`;
  }
  const verb = mode === "completed" ? "completed" : "created";
  if (period === "day") {
    return `Nothing was ${verb} on this day.`;
  }
  return `Nothing was ${verb} in this ${period}.`;
}

function weekLabel(monday) {
  const sunday = addDays(monday, 6);
  const [startYear, startMonth, startDay] = monday.split("-").map(Number);
  const [endYear, endMonth, endDay] = sunday.split("-").map(Number);
  const start = `${MONTHS[startMonth - 1]} ${startDay}`;
  const end = `${MONTHS[endMonth - 1]} ${endDay}`;
  if (startYear !== endYear) {
    return `${start}, ${startYear} – ${end}, ${endYear}`;
  }
  if (startMonth !== endMonth) {
    return `${start} – ${end}, ${startYear}`;
  }
  return `${MONTHS[startMonth - 1]} ${startDay}–${endDay}, ${startYear}`;
}

function dayHeading(iso) {
  const [year, month, day] = iso.split("-").map(Number);
  return `${WEEKDAYS[weekdayIndex(iso)]}, ${MONTHS[month - 1]} ${day}, ${year}`;
}

function periodLabel(view, focus) {
  if (view === "week") {
    return weekLabel(mondayOf(focus));
  }
  if (view === "day") {
    return dayHeading(focus);
  }
  const [year, month] = monthStart(focus).split("-").map(Number);
  return `${MONTHS[month - 1]} ${year}`;
}

function barsFor(issues, mode, completedAt, offsetMinutes, start, end) {
  const bars = [];
  for (const issue of issues) {
    const bar = placed(issue, mode, completedAt, offsetMinutes);
    if (bar && overlaps(bar, start, end)) {
      bars.push({ issue, bar });
    }
  }
  bars.sort(compareBars);
  return bars;
}

function dayIssues(bars, day, withTime) {
  return bars
    .filter((item) => item.bar.start <= day && item.bar.end >= day)
    .map((item) => chip(item.issue, item.bar, day, withTime));
}

function monthWeeks(focus, today, bars) {
  const first = monthStart(focus);
  const last = monthEnd(first);
  let cursor = mondayOf(first);
  const weeks = [];
  while (cursor <= last) {
    const days = [];
    for (let offset = 0; offset < 7; offset += 1) {
      const date = addDays(cursor, offset);
      days.push({
        date,
        number: Number(date.slice(8)),
        inMonth: date.slice(0, 7) === first.slice(0, 7),
        isToday: date === today,
        issues: dayIssues(bars, date, false),
      });
    }
    weeks.push({ days });
    cursor = addDays(cursor, 7);
  }
  return weeks;
}

function listedDays(start, count, today, bars) {
  const days = [];
  for (let offset = 0; offset < count; offset += 1) {
    const date = addDays(start, offset);
    days.push({
      date,
      weekday: WEEKDAYS[weekdayIndex(date)],
      heading: dayHeading(date),
      isToday: date === today,
      issues: dayIssues(bars, date, true),
    });
  }
  return days;
}

function calendarView({
  library,
  remote,
  completedAt,
  mode,
  view,
  focus,
  today,
  projectId = null,
  userId,
  offsetMinutes = 0,
  filter,
}) {
  const shownView = parseView(view);
  const shownMode = parseMode(mode);
  const shownToday = parseDay(today, "1970-01-01");
  const shownFocus = parseDay(focus, shownToday);
  const online = Array.isArray(remote);
  const issues = online
    ? onlineIssues(library, remote, projectId, userId, filter)
    : savedIssues(library, projectId, userId, filter);
  let rangeStart = shownFocus;
  let rangeEnd = shownFocus;
  if (shownView === "month") {
    const first = monthStart(shownFocus);
    rangeStart = mondayOf(first);
    rangeEnd = addDays(mondayOf(monthEnd(first)), 6);
  } else if (shownView === "week") {
    rangeStart = mondayOf(shownFocus);
    rangeEnd = addDays(rangeStart, 6);
  }
  const bars = barsFor(issues, shownMode, completedAt, offsetMinutes, rangeStart, rangeEnd);
  const period = shownView === "month" ? "month" : shownView;
  return {
    label: periodLabel(shownView, shownFocus),
    view: shownView,
    mode: shownMode,
    focus: shownFocus,
    banner: online ? "" : NEEDS_CONNECTION,
    empty: bars.length ? "" : emptyNote(shownMode, period),
    weekdays: WEEKDAYS_SHORT,
    weeks: shownView === "month" ? monthWeeks(shownFocus, shownToday, bars) : [],
    days: shownView === "week"
      ? listedDays(mondayOf(shownFocus), 7, shownToday, bars)
      : shownView === "day"
        ? listedDays(shownFocus, 1, shownToday, bars)
        : [],
    projects: enabledProjects(library).map((project) => ({ id: project.id, key: project.key })),
  };
}

function moveFocus(view, focus, today, direction) {
  const shownView = parseView(view);
  const shownToday = parseDay(today, "1970-01-01");
  const shownFocus = parseDay(focus, shownToday);
  if (direction === "today") {
    return shownToday;
  }
  if (shownView === "week") {
    return addDays(mondayOf(shownFocus), 7 * direction);
  }
  if (shownView === "day") {
    return addDays(shownFocus, direction);
  }
  return shiftMonth(shownFocus, direction);
}

function focusForView(nextView, currentView, focus, today) {
  const shownNext = parseView(nextView);
  const shownCurrent = parseView(currentView);
  const shownToday = parseDay(today, "1970-01-01");
  const shownFocus = parseDay(focus, shownToday);
  if (shownCurrent === "month" && shownNext !== "month") {
    const start = monthStart(shownFocus);
    const end = monthEnd(start);
    if (shownToday >= start && shownToday <= end) {
      return shownToday;
    }
    return start;
  }
  return shownFocus;
}

module.exports = {
  NEEDS_CONNECTION,
  calendarView,
  focusForView,
  moveFocus,
};
