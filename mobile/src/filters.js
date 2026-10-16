const TYPES = [
  ["epic", "Epic"],
  ["story", "Story"],
  ["subtask", "Subtask"],
];
const STATUSES = [
  ["todo", "To Do"],
  ["in_progress", "In Progress"],
  ["in_review", "In Review"],
  ["blocked", "Blocked"],
  ["done", "Done"],
  ["cancelled", "Cancelled"],
];
const PRIORITIES = [
  ["p1", "P1 — Blocker"],
  ["p2", "P2 — Critical"],
  ["p3", "P3 — Major"],
  ["p4", "P4 — Minor"],
  ["p5", "P5 — Trivial"],
];
const SPRINT_STATES = { planned: "Planned", active: "Active" };

function blankFilter() {
  return {
    types: ["epic", "story", "subtask"],
    statuses: [],
    priorities: [],
    sprints: [],
    projects: [],
    assignees: [],
    reporters: [],
    labels: [],
  };
}

function matchesIssue(raw, filter, options = {}) {
  if (!filter || !raw) {
    return true;
  }
  const types = filter.types || [];
  if (!types.includes(raw.type)) {
    return false;
  }
  if ((filter.statuses || []).length && !(filter.statuses || []).includes(raw.status)) {
    return false;
  }
  if ((filter.priorities || []).length && !(filter.priorities || []).includes(raw.priority)) {
    return false;
  }
  const sprints = filter.sprints || [];
  if (sprints.length) {
    const token = raw.sprint_id == null ? "unscheduled" : String(raw.sprint_id);
    if (!sprints.includes(token)) {
      return false;
    }
  }
  const labels = filter.labels || [];
  if (labels.length) {
    const names = raw.labels || [];
    const named = names.some((name) => labels.includes(name));
    const unlabeled = labels.includes("unlabeled") && !names.length;
    if (!named && !unlabeled) {
      return false;
    }
  }
  const assignees = filter.assignees || [];
  if (assignees.length) {
    const token = raw.assignee_id == null ? "unassigned" : String(raw.assignee_id);
    if (!assignees.includes(token)) {
      return false;
    }
  }
  const reporters = filter.reporters || [];
  if (reporters.length) {
    const token = raw.reporter_id == null ? "none" : String(raw.reporter_id);
    if (!reporters.includes(token)) {
      return false;
    }
  }
  const projects = filter.projects || [];
  if (!options.ignoreProject && projects.length) {
    const id = raw.project_id != null ? raw.project_id : options.projectId;
    if (!projects.includes(String(id))) {
      return false;
    }
  }
  return true;
}

function choiceSummary(selected, options, emptyLabel) {
  const chosen = selected || [];
  if (!chosen.length) {
    return emptyLabel;
  }
  const known = new Set((options || []).map(([value]) => value));
  const labels = (options || []).filter(([value]) => chosen.includes(value)).map(([, label]) => label);
  const extra = chosen.filter((value) => !known.has(value));
  if (options && options.length && !extra.length && labels.length === options.length) {
    return "All";
  }
  return [...labels, ...extra].join(", ") || emptyLabel;
}

function filterMenus(filter, choices, showProject) {
  const menus = [
    { id: "types", title: "Type", empty: "None", options: TYPES },
    { id: "statuses", title: "Status", empty: "Any", options: STATUSES },
    { id: "priorities", title: "Priority", empty: "Any", options: PRIORITIES },
    { id: "sprints", title: "Sprint", empty: "Any", options: (choices && choices.sprints) || [] },
  ];
  if (showProject) {
    menus.push({
      id: "projects",
      title: "Project",
      empty: "Any",
      options: (choices && choices.projects) || [],
    });
  }
  menus.push(
    { id: "assignees", title: "Assignee", empty: "Any", options: (choices && choices.assignees) || [] },
    { id: "reporters", title: "Created by", empty: "Any", options: (choices && choices.reporters) || [] },
    { id: "labels", title: "Label", empty: "Any", options: (choices && choices.labels) || [] },
  );
  return menus.map((menu) => ({
    ...menu,
    summary: choiceSummary(filter[menu.id], menu.options, menu.empty),
  }));
}

function toggleChoice(filter, field, value) {
  const token = String(value);
  const current = filter[field] || [];
  const next = current.includes(token)
    ? current.filter((item) => item !== token)
    : [...current, token];
  return { ...filter, [field]: next };
}

function sprintOptions(library, fetched, projectId) {
  const rows = new Map();
  function add(sprint, projectKey, ownerId) {
    if (!sprint || sprint.state === "completed" || sprint.id == null) {
      return;
    }
    if (projectId != null && Number(ownerId) !== Number(projectId)) {
      return;
    }
    const prefix = projectId == null && projectKey ? `${projectKey} / ` : "";
    const state = SPRINT_STATES[sprint.state] || "";
    rows.set(String(sprint.id), state ? `${prefix}${sprint.name} (${state})` : `${prefix}${sprint.name}`);
  }
  for (const project of Object.values((library && library.projects) || {})) {
    if (!project || project.enabled === false || !project.sprint) {
      continue;
    }
    add(project.sprint, project.key, project.id);
  }
  for (const sprint of fetched || []) {
    add(sprint, sprint.projectKey, sprint.projectId != null ? sprint.projectId : sprint.project_id);
  }
  return [["unscheduled", "Unscheduled"], ...[...rows.entries()].sort((left, right) => left[1].localeCompare(right[1]))];
}

function projectOptions(library) {
  return Object.values((library && library.projects) || {})
    .filter((project) => project && project.enabled !== false)
    .sort((left, right) => String(left.key || "").localeCompare(String(right.key || "")))
    .map((project) => [String(project.id), project.key]);
}

function peopleOptions(library, emptyValue, emptyLabel) {
  const people = ((library && library.people) || [])
    .filter((person) => person && person.id != null)
    .slice()
    .sort((left, right) => String(left.display_name || "").localeCompare(String(right.display_name || "")));
  return [[emptyValue, emptyLabel], ...people.map((person) => [String(person.id), person.display_name])];
}

function labelOptions(library) {
  const names = new Set();
  for (const label of (library && library.labels) || []) {
    const name = typeof label === "string" ? label : label && label.name;
    if (name) {
      names.add(name);
    }
  }
  for (const project of Object.values((library && library.projects) || {})) {
    for (const issue of Object.values((project && project.issues) || {})) {
      for (const name of ((issue && issue.raw && issue.raw.labels) || [])) {
        if (name) {
          names.add(name);
        }
      }
    }
  }
  return [["unlabeled", "Unlabeled"], ...[...names].sort().map((name) => [name, name])];
}

module.exports = {
  PRIORITIES,
  STATUSES,
  TYPES,
  blankFilter,
  filterMenus,
  labelOptions,
  matchesIssue,
  peopleOptions,
  projectOptions,
  sprintOptions,
  toggleChoice,
};
