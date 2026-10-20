const { statusLabel } = require("./work");

const CLOSED = new Set(["done", "cancelled"]);
const STATUS_ORDER = ["todo", "in_progress", "in_review", "blocked", "done", "cancelled"];
const SECTIONS = [
  ["due", "Due or overdue", true],
  ["week", "Due this week", true],
  ["month", "Due this month", true],
  ["starting", "Starting or started", true],
  ["assigned", "Assigned to me", true],
  ["blocked", "Blocked", true],
  ["sprint", "In the active sprint", false],
  ["waiting", "Waiting this cycle", true],
  ["completed", "Completed today", true],
];

const SAVED_SPRINT = "Showing issues saved from active sprints. A section that needs other issues needs a connection.";
const OTHER_ISSUES = "Other issues in this section need a connection.";
const NOTHING_ASSIGNED = "Nothing is assigned to you.";
const NOTHING_SAVED = "Nothing in the saved sprint is assigned to you.";

function addDays(iso, days) {
  const [year, month, day] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function monthEnd(iso) {
  const [year, month] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(year, month, 0));
  return date.toISOString().slice(0, 10);
}

function calendarDay(value) {
  const matched = /^(\d{4}-\d{2}-\d{2})/.exec(String(value || ""));
  return matched ? matched[1] : null;
}

function localCalendarDay(value, offsetMinutes) {
  if (!value) {
    return null;
  }
  const text = String(value);
  const utc = /Z$|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`;
  const parsed = Date.parse(utc);
  if (Number.isNaN(parsed)) {
    return calendarDay(value);
  }
  const local = new Date(parsed - offsetMinutes * 60 * 1000);
  return local.toISOString().slice(0, 10);
}

function issueNumber(issue) {
  if (Number.isInteger(issue.number)) {
    return issue.number;
  }
  const matched = /-(\d+)$/.exec(issue.key || "");
  return matched ? Number(matched[1]) : 0;
}

function byKey(left, right) {
  const project = (left.projectKey || "").localeCompare(right.projectKey || "");
  if (project) {
    return project;
  }
  return issueNumber(left) - issueNumber(right);
}

function byDate(field) {
  return (left, right) => {
    const compared = (left[field] || "").localeCompare(right[field] || "");
    return compared || byKey(left, right);
  };
}

function present(raw, project, pending, activeSprintId) {
  return {
    id: raw.id,
    key: raw.key || "",
    number: raw.number,
    title: raw.title || "",
    projectKey: project ? project.key : "",
    status: raw.status,
    statusLabel: statusLabel(raw.status),
    dueOn: calendarDay(raw.due_at),
    startOn: calendarDay(raw.start_at),
    occurrenceOn: calendarDay(raw.occurrence_on),
    seriesId: raw.series_id || null,
    sprintId: raw.sprint_id || null,
    inActiveSprint: activeSprintId != null && raw.sprint_id === activeSprintId,
    blockers: raw.unresolved_blockers || 0,
    pending: Boolean(pending),
    completedOn: raw.completedOn || null,
    assigneeId: raw.assignee_id,
  };
}

function savedIssues(library, userId) {
  const rows = [];
  for (const project of Object.values((library && library.projects) || {})) {
    if (!project.enabled) {
      continue;
    }
    const activeSprintId = project.sprint ? project.sprint.id : null;
    for (const record of Object.values(project.issues || {})) {
      const raw = record.raw || {};
      if (Number(raw.assignee_id) !== Number(userId)) {
        continue;
      }
      rows.push(present(raw, project, record.pending || record.conflict, activeSprintId));
    }
  }
  return rows;
}

function mergeRemote(library, userId, remote) {
  const byId = new Map();
  const projects = (library && library.projects) || {};
  for (const raw of remote || []) {
    if (Number(raw.assignee_id) !== Number(userId)) {
      continue;
    }
    const project = projects[raw.project_id] || { key: raw.projectKey || "", sprint: null };
    if (projects[raw.project_id] && !projects[raw.project_id].enabled) {
      continue;
    }
    const activeSprintId = project.sprint ? project.sprint.id : null;
    byId.set(raw.id, present(raw, project, false, activeSprintId));
  }
  for (const row of savedIssues(library, userId)) {
    if (row.pending || row.id < 0) {
      byId.set(row.id, row);
    }
  }
  return [...byId.values()];
}

function fullySaved(library) {
  const projects = Object.values((library && library.projects) || {}).filter(
    (project) => project.enabled,
  );
  return projects.length > 0 && projects.every((project) => project.catalog);
}

function inboxView({ library, userId, today, remote, offsetMinutes = 0 }) {
  const online = Array.isArray(remote);
  const savedAll = fullySaved(library);
  const issues = online ? mergeRemote(library, userId, remote) : savedIssues(library, userId);
  const weekEnd = addDays(today, 7);
  const endOfMonth = monthEnd(today);
  const unfinished = issues.filter((issue) => !CLOSED.has(issue.status));
  const grouped = {
    due: unfinished.filter((issue) => issue.dueOn && issue.dueOn <= today).sort(byDate("dueOn")),
    week: unfinished.filter((issue) => issue.dueOn && today < issue.dueOn && issue.dueOn <= weekEnd).sort(byDate("dueOn")),
    month: unfinished.filter((issue) => issue.dueOn && weekEnd < issue.dueOn && issue.dueOn <= endOfMonth).sort(byDate("dueOn")),
    starting: unfinished.filter((issue) => issue.startOn && issue.startOn <= today).sort(byDate("startOn")),
    assigned: [...unfinished].sort(byKey),
    blocked: unfinished.filter((issue) => issue.status === "blocked" || issue.blockers > 0).sort(byKey),
    sprint: issues.filter((issue) => issue.inActiveSprint).sort((left, right) => {
      const status = STATUS_ORDER.indexOf(left.status) - STATUS_ORDER.indexOf(right.status);
      return status || byKey(left, right);
    }),
    waiting: unfinished.filter((issue) => issue.seriesId && issue.occurrenceOn && issue.occurrenceOn <= today).sort(byDate("occurrenceOn")),
    completed: online || savedAll
      ? issues.filter((issue) => issue.status === "done" && localCalendarDay(issue.completedOn, offsetMinutes) === today).sort(byKey)
      : [],
  };
  const sections = [];
  for (const [key, title, outside] of SECTIONS) {
    const rows = grouped[key];
    if (!rows.length) {
      continue;
    }
    sections.push({
      key,
      title,
      needsConnection: !online && !savedAll && outside,
      rows: rows.map((issue) => ({
        id: issue.id,
        key: issue.key,
        title: issue.title,
        projectKey: issue.projectKey,
        status: issue.status,
        statusLabel: issue.statusLabel,
        pending: issue.pending,
        blockers: issue.blockers,
      })),
    });
  }
  return {
    online,
    banner: online ? "" : savedAll ? "Showing the saved copy." : SAVED_SPRINT,
    empty: sections.length ? "" : online || savedAll ? NOTHING_ASSIGNED : NOTHING_SAVED,
    needsConnection: OTHER_ISSUES,
    sections,
  };
}

module.exports = {
  NOTHING_ASSIGNED,
  NOTHING_SAVED,
  OTHER_ISSUES,
  SAVED_SPRINT,
  SECTIONS,
  inboxView,
  localCalendarDay,
};
