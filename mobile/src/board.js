const { matchesIssue } = require("./filters");
const { statusLabel } = require("./work");

const COLUMNS = [
  ["todo", "To Do"],
  ["in_progress", "In Progress"],
  ["in_review", "In Review"],
  ["blocked", "Blocked"],
  ["done", "Done"],
  ["cancelled", "Cancelled"],
];

const TYPE_LABELS = {
  epic: "Epic",
  story: "Story",
  subtask: "Subtask",
};

const SAVED_BOARD = "Showing the saved active sprint. Other board issues need a connection.";
const NOTHING = "Nothing to show.";

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

function personName(people, assigneeId) {
  if (!assigneeId) {
    return "Unassigned";
  }
  const found = (people || []).find((person) => person.id === assigneeId);
  return found && found.display_name ? found.display_name : "Unassigned";
}

function sprintLabel(project, name, master) {
  if (!name) {
    return null;
  }
  return master ? `${project.key} / ${name}` : name;
}

function laneNames(boards) {
  const names = new Map();
  for (const board of boards || []) {
    for (const lane of board.lanes || []) {
      if (lane.sprint_id != null && lane.name) {
        names.set(lane.sprint_id, lane.name);
      }
    }
  }
  return names;
}

function nameForSprint(raw, project, names, master) {
  if (!raw.sprint_id) {
    return sprintLabel(project, "Unscheduled", master);
  }
  const known = names.get(raw.sprint_id);
  if (known) {
    return sprintLabel(project, known, master);
  }
  if (project.sprint && project.sprint.id === raw.sprint_id) {
    return sprintLabel(project, project.sprint.name, master);
  }
  return null;
}

function present(raw, project, pending, sprintName, people) {
  return {
    id: raw.id,
    key: raw.key || "",
    projectKey: project.key || "",
    number: issueNumber(raw),
    title: raw.title || "",
    status: raw.status,
    statusLabel: statusLabel(raw.status),
    typeLabel: TYPE_LABELS[raw.type] || raw.type || "",
    priority: String(raw.priority || "").toUpperCase(),
    assignee: personName(people, raw.assignee_id),
    sprintName,
    blockers: raw.unresolved_blockers || 0,
    pending: Boolean(pending),
  };
}

function byCard(left, right) {
  const project = left.projectKey.localeCompare(right.projectKey);
  if (project) {
    return project;
  }
  return left.number - right.number;
}

function localIssues(projects) {
  const records = new Map();
  for (const project of projects) {
    for (const issue of Object.values(project.issues || {})) {
      records.set(issue.id, { issue, project });
    }
  }
  return records;
}

function savedCards(projects, people, master, filter, scoped) {
  const cards = [];
  for (const project of projects) {
    const sprint = project.sprint;
    if (!sprint) {
      continue;
    }
    for (const issue of Object.values(project.issues || {})) {
      const raw = issue.raw || {};
      if (raw.sprint_id !== sprint.id) {
        continue;
      }
      if (!matchesIssue(raw, filter, { projectId: project.id, ignoreProject: scoped })) {
        continue;
      }
      cards.push(
        present(
          raw,
          project,
          issue.pending || issue.conflict || raw.id < 0,
          sprintLabel(project, sprint.name, master),
          people,
        ),
      );
    }
  }
  return cards;
}

function remoteCards(boards, projects, people, master, filter, scoped) {
  const allowed = new Map(projects.map((project) => [project.id, project]));
  const names = laneNames(boards);
  const locals = localIssues(projects);
  const cards = [];
  const seen = new Set();
  for (const board of boards || []) {
    const project = allowed.get(board.project_id);
    if (!project) {
      continue;
    }
    for (const column of board.columns || []) {
      for (const issue of column.issues || []) {
        const local = locals.get(issue.id);
        const waiting = local && (local.issue.pending || local.issue.conflict);
        const raw = waiting ? local.issue.raw : issue;
        const home = waiting ? local.project : project;
        seen.add(raw.id);
        if (!matchesIssue(raw, filter, { projectId: home.id, ignoreProject: scoped })) {
          continue;
        }
        cards.push(
          present(
            raw,
            home,
            waiting || raw.id < 0,
            nameForSprint(raw, home, names, master),
            people,
          ),
        );
      }
    }
  }
  for (const [id, local] of locals) {
    if (seen.has(id)) {
      continue;
    }
    const raw = local.issue.raw || {};
    if (!(local.issue.pending || local.issue.conflict || id < 0)) {
      continue;
    }
    if (!matchesIssue(raw, filter, { projectId: local.project.id, ignoreProject: scoped })) {
      continue;
    }
    cards.push(
      present(
        raw,
        local.project,
        true,
        nameForSprint(raw, local.project, names, master),
        people,
      ),
    );
  }
  return cards;
}

function boardView({ library, boards, projectId, filter }) {
  const projects = enabledProjects(library);
  const chosen =
    projectId == null ? projects : projects.filter((project) => project.id === projectId);
  const selected = projectId == null ? null : projects.find((project) => project.id === projectId) || null;
  const people = (library && library.people) || [];
  const online = Array.isArray(boards);
  const master = projectId == null;
  const scoped = projectId != null;
  const cards = online
    ? remoteCards(boards, chosen, people, master, filter, scoped)
    : savedCards(chosen, people, master, filter, scoped);
  return {
    title: selected ? `${selected.key} board` : "Board",
    projects: projects.map((project) => ({ id: project.id, key: project.key })),
    banner: online ? "" : SAVED_BOARD,
    empty: cards.length ? "" : NOTHING,
    columns: COLUMNS.map(([status, label]) => ({
      status,
      label,
      cards: cards.filter((card) => card.status === status).sort(byCard),
    })),
  };
}

module.exports = {
  NOTHING,
  SAVED_BOARD,
  boardView,
};
