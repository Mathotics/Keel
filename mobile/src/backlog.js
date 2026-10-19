const { statusLabel } = require("./work");

const CLOSED = new Set(["done", "cancelled"]);
const TYPE_LABELS = {
  epic: "Epic",
  story: "Story",
  subtask: "Subtask",
};
const STATE_LABELS = {
  active: "Active",
  planned: "Planned",
};

const NEEDS_CONNECTION = "The backlog needs a connection.";
const SAVED_BACKLOG = "Showing the saved copy.";
const NOTHING = "Nothing in the backlog.";
const NO_SPRINT = "No active or planned sprint";

function enabledProjects(library) {
  return Object.values((library && library.projects) || {})
    .filter((project) => project && project.enabled)
    .sort((left, right) => (left.key || "").localeCompare(right.key || ""));
}

function personName(people, assigneeId) {
  if (!assigneeId) {
    return "Unassigned";
  }
  const found = (people || []).find((person) => person.id === assigneeId);
  return found && found.display_name ? found.display_name : "Unknown";
}

function formatWhen(value) {
  if (!value) {
    return "";
  }
  const text = String(value);
  const utc = /Z$|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`;
  const date = new Date(utc);
  if (Number.isNaN(date.getTime())) {
    return text;
  }
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`;
}

function present(raw, pending, people) {
  return {
    id: raw.id,
    key: raw.key || "",
    title: raw.title || "",
    typeLabel: TYPE_LABELS[raw.type] || raw.type || "",
    priority: String(raw.priority || "").toUpperCase(),
    status: raw.status,
    statusLabel: statusLabel(raw.status),
    assignee: personName(people, raw.assignee_id),
    start: formatWhen(raw.start_at),
    due: formatWhen(raw.due_at),
    blockers: raw.unresolved_blockers || 0,
    pending: Boolean(pending),
    createdAt: raw.created_at || "",
  };
}

function byAge(left, right) {
  const created = left.createdAt.localeCompare(right.createdAt);
  if (created) {
    return created;
  }
  return left.id - right.id;
}

function waitingIssues(project) {
  const records = new Map();
  for (const issue of Object.values((project && project.issues) || {})) {
    if (issue.pending || issue.conflict || issue.id < 0) {
      records.set(issue.id, issue);
    }
  }
  return records;
}

function onBacklog(raw) {
  return raw && !raw.sprint_id && !CLOSED.has(raw.status);
}

function rowsFor(project, issues, people) {
  const waiting = waitingIssues(project);
  const rows = [];
  const seen = new Set();
  for (const issue of issues || []) {
    const local = waiting.get(issue.id);
    if (local) {
      const raw = local.issue ? local.issue.raw : local.raw;
      if (onBacklog(raw)) {
        rows.push(present(raw, true, people));
      }
      seen.add(issue.id);
      continue;
    }
    if (onBacklog(issue)) {
      rows.push(present(issue, false, people));
      seen.add(issue.id);
    }
  }
  for (const [id, local] of waiting) {
    if (seen.has(id)) {
      continue;
    }
    const raw = local.raw || {};
    if (onBacklog(raw)) {
      rows.push(present(raw, true, people));
    }
  }
  return rows.sort(byAge);
}

function sprintChoices(sprints, projectId) {
  return (sprints || [])
    .filter(
      (sprint) =>
        sprint &&
        sprint.project_id === projectId &&
        (sprint.state === "active" || sprint.state === "planned"),
    )
    .map((sprint) => ({
      id: sprint.id,
      name: sprint.name,
      state: sprint.state,
      label: `${sprint.name} (${STATE_LABELS[sprint.state]})`,
    }));
}

function localRows(project, people) {
  return Object.values((project && project.issues) || {})
    .filter((issue) => onBacklog(issue.raw))
    .map((issue) => present(issue.raw, issue.pending || issue.conflict, people))
    .sort(byAge);
}

function backlogView({ library, projectId, issues, sprints }) {
  const projects = enabledProjects(library);
  const selected =
    projectId == null
      ? projects[0] || null
      : projects.find((project) => project.id === projectId) || null;
  const people = (library && library.people) || [];
  const online = Array.isArray(issues);
  const saved = Boolean(selected && (selected.catalog || selected.saved));
  const choices = online && selected ? sprintChoices(sprints, selected.id) : [];
  const rows = online && selected ? rowsFor(selected, issues, people) : localRows(selected, people);
  return {
    title: selected ? `${selected.key} backlog` : "Backlog",
    projects: projects.map((project) => ({ id: project.id, key: project.key })),
    selectedProjectId: selected ? selected.id : null,
    banner: online ? "" : saved ? SAVED_BACKLOG : NEEDS_CONNECTION,
    empty: rows.length === 0 && (online || saved) ? NOTHING : "",
    noSprint: online && rows.length > 0 && choices.length === 0 ? NO_SPRINT : "",
    sprints: choices,
    rows,
  };
}

module.exports = {
  NEEDS_CONNECTION,
  NOTHING,
  NO_SPRINT,
  backlogView,
};
