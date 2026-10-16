const { matchesIssue } = require("./filters");
const { statusLabel } = require("./work");

const STATES = [
  ["planned", "Planned"],
  ["active", "Active"],
  ["completed", "Completed"],
];

const TYPE_LABELS = {
  epic: "Epic",
  story: "Story",
  subtask: "Subtask",
};

const NEEDS_CONNECTION = "Planned and completed sprints need a connection.";
const SAVED_ACTIVE = "The active sprint is the saved copy.";
const NONE = "None.";
const NO_ISSUES = "No issues in this sprint.";
const NAME_REQUIRED = "A sprint needs a name.";
const BAD_DATE = "A sprint date could not be read.";
const BAD_RANGE = "A sprint cannot end before it starts.";

function enabledProjects(library) {
  return Object.values((library && library.projects) || {})
    .filter((project) => project && project.enabled)
    .sort((left, right) => (left.key || "").localeCompare(right.key || ""));
}

function selectedProject(library, projectId) {
  const projects = enabledProjects(library);
  if (projectId == null) {
    return projects[0] || null;
  }
  return projects.find((project) => project.id === projectId) || null;
}

function dateOnly(value) {
  if (!value) {
    return null;
  }
  const matched = /^(\d{4}-\d{2}-\d{2})/.exec(String(value));
  return matched ? matched[1] : null;
}

function readDate(raw) {
  const cleaned = String(raw || "").trim();
  if (!cleaned) {
    return { value: null };
  }
  const matched = /^(\d{4})-(\d{2})-(\d{2})$/.exec(cleaned);
  if (!matched) {
    return { error: BAD_DATE };
  }
  const year = Number(matched[1]);
  const month = Number(matched[2]);
  const day = Number(matched[3]);
  const date = new Date(Date.UTC(year, month - 1, day));
  if (
    date.getUTCFullYear() !== year ||
    date.getUTCMonth() !== month - 1 ||
    date.getUTCDate() !== day
  ) {
    return { error: BAD_DATE };
  }
  return { value: cleaned };
}

function sprintCard(sprint) {
  return {
    id: sprint.id,
    name: sprint.name || "",
    goal: sprint.goal || "",
    state: sprint.state,
    starts: dateOnly(sprint.starts_on) || "",
    ends: dateOnly(sprint.ends_on) || "",
  };
}

function planningView({ library, projectId, sprints }) {
  const projects = enabledProjects(library);
  const selected = selectedProject(library, projectId);
  const online = Array.isArray(sprints);
  const grouped = Object.fromEntries(STATES.map(([state]) => [state, []]));
  if (online) {
    for (const sprint of sprints) {
      if (selected && sprint.project_id === selected.id && grouped[sprint.state]) {
        grouped[sprint.state].push(sprintCard(sprint));
      }
    }
  } else if (selected && selected.sprint && selected.sprint.state === "active") {
    grouped.active.push(sprintCard(selected.sprint));
  }
  return {
    title: selected ? `${selected.key} sprints` : "Sprints",
    projects: projects.map((project) => ({ id: project.id, key: project.key })),
    selectedProjectId: selected ? selected.id : null,
    banner: online ? "" : `${NEEDS_CONNECTION} ${SAVED_ACTIVE}`,
    canPlan: online && Boolean(selected),
    sections: STATES.map(([state, label]) => ({
      key: state,
      label,
      needsConnection: !online && state !== "active",
      empty: online && grouped[state].length === 0 ? NONE : "",
      sprints: grouped[state],
    })),
  };
}

function personName(people, assigneeId) {
  if (!assigneeId) {
    return "Unassigned";
  }
  const found = (people || []).find((person) => person.id === assigneeId);
  return found && found.display_name ? found.display_name : "Unknown";
}

function issueNumber(issue) {
  if (Number.isInteger(issue.number)) {
    return issue.number;
  }
  const matched = /-(\d+)$/.exec(issue.key || "");
  return matched ? Number(matched[1]) : 0;
}

function presentIssue(raw, pending, people) {
  return {
    id: raw.id,
    key: raw.key || "",
    number: issueNumber(raw),
    title: raw.title || "",
    typeLabel: TYPE_LABELS[raw.type] || raw.type || "",
    priority: String(raw.priority || "").toUpperCase(),
    status: raw.status,
    statusLabel: statusLabel(raw.status),
    assignee: personName(people, raw.assignee_id),
    pending: Boolean(pending),
  };
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

function savedIssues(project, sprintId, people, filter) {
  return Object.values((project && project.issues) || {})
    .filter((issue) => issue.raw && issue.raw.sprint_id === sprintId && matchesIssue(issue.raw, filter, { ignoreProject: true }))
    .map((issue) => presentIssue(issue.raw, issue.pending || issue.conflict || issue.raw.id < 0, people))
    .sort((left, right) => left.number - right.number);
}

function mergedIssues(project, sprintId, remote, people, filter) {
  const waiting = waitingIssues(project);
  const rows = [];
  const seen = new Set();
  for (const issue of remote || []) {
    const local = waiting.get(issue.id);
    if (local) {
      const raw = local.raw || {};
      if (raw.sprint_id === sprintId && matchesIssue(raw, filter, { ignoreProject: true })) {
        rows.push(presentIssue(raw, true, people));
      }
      seen.add(issue.id);
      continue;
    }
    if (matchesIssue(issue, filter, { ignoreProject: true })) {
      rows.push(presentIssue(issue, false, people));
    }
    seen.add(issue.id);
  }
  for (const [id, local] of waiting) {
    if (seen.has(id)) {
      continue;
    }
    const raw = local.raw || {};
    if (raw.sprint_id === sprintId && matchesIssue(raw, filter, { ignoreProject: true })) {
      rows.push(presentIssue(raw, true, people));
    }
  }
  return rows.sort((left, right) => left.number - right.number);
}

function sprintDetail({ library, projectId, sprint, online, filter }) {
  const project = selectedProject(library, projectId);
  const people = (library && library.people) || [];
  const connected = Boolean(online && sprint && Array.isArray(sprint.issues));
  const rows = !sprint
    ? []
    : connected
      ? mergedIssues(project, sprint.id, sprint.issues, people, filter)
      : savedIssues(project, sprint.id, people, filter);
  return {
    id: sprint ? sprint.id : null,
    name: sprint ? sprint.name || "" : "",
    goal: sprint && sprint.goal ? sprint.goal : "",
    state: sprint ? sprint.state : "",
    stateLabel: sprint ? (STATES.find(([state]) => state === sprint.state) || ["", sprint.state])[1] : "",
    starts: sprint ? dateOnly(sprint.starts_on) || "" : "",
    ends: sprint ? dateOnly(sprint.ends_on) || "" : "",
    editable: connected,
    canStart: connected && sprint.state === "planned",
    canComplete: connected && sprint.state === "active",
    empty: rows.length ? "" : NO_ISSUES,
    rows,
  };
}

function prepareSprint(draft) {
  const name = String((draft && draft.name) || "").trim();
  if (!name) {
    return { error: NAME_REQUIRED };
  }
  const start = readDate(draft.startsOn);
  if (start.error) {
    return start;
  }
  const end = readDate(draft.endsOn);
  if (end.error) {
    return end;
  }
  if (start.value && end.value && end.value < start.value) {
    return { error: BAD_RANGE };
  }
  return {
    body: {
      name: name.slice(0, 200),
      goal: String(draft.goal || "").trim(),
      starts_on: start.value,
      ends_on: end.value,
    },
  };
}

function prepareSprintUpdate(sprint, draft) {
  const prepared = prepareSprint(draft);
  if (prepared.error) {
    return prepared;
  }
  const changes = {};
  if (prepared.body.name !== (sprint.name || "")) {
    changes.name = prepared.body.name;
  }
  if (prepared.body.goal !== (sprint.goal || "")) {
    changes.goal = prepared.body.goal;
  }
  if (prepared.body.starts_on !== dateOnly(sprint.starts_on)) {
    changes.starts_on = prepared.body.starts_on;
  }
  if (prepared.body.ends_on !== dateOnly(sprint.ends_on)) {
    changes.ends_on = prepared.body.ends_on;
  }
  return { changes };
}

function completionNotice(result, sprints) {
  const count = (result && result.carried_over) || 0;
  if (!count) {
    return "No unfinished issues to carry.";
  }
  const noun = count === 1 ? "issue" : "issues";
  const destination = result.carried_to_sprint_id;
  if (!destination) {
    return `${count} unfinished ${noun} returned to the backlog.`;
  }
  const found = (sprints || []).find((sprint) => sprint.id === destination);
  return `${count} unfinished ${noun} moved to ${found ? found.name : "the next sprint"}.`;
}

module.exports = {
  BAD_DATE,
  BAD_RANGE,
  NAME_REQUIRED,
  NEEDS_CONNECTION,
  NO_ISSUES,
  NONE,
  SAVED_ACTIVE,
  completionNotice,
  planningView,
  prepareSprint,
  prepareSprintUpdate,
  sprintDetail,
};
