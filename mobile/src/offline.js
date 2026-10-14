const { issuePage } = require("./issue");
const { statusLabel } = require("./work");

const NOT_ON_SERVER = "Not on the server yet.";

function emptyStore() {
  return { projects: {}, people: [], labels: [], queue: [] };
}

function storeKey(userId) {
  return `keel.offline.${userId}`;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function projectList(store) {
  return Object.values(store.projects || {}).sort((left, right) =>
    left.key.localeCompare(right.key),
  );
}

function findIssue(store, issueId) {
  for (const project of Object.values(store.projects || {})) {
    if (project.issues[issueId]) {
      return project.issues[issueId];
    }
  }
  return null;
}

function hasWaiting(store, projectId) {
  return (store.queue || []).some(
    (item) => projectId == null || item.projectId === projectId,
  );
}

function pageFromSnapshot(issue, issues, people, sprint) {
  const parent = (issues || []).find((item) => item.id === issue.parent_id) || null;
  const children = (issues || []).filter((item) => item.parent_id === issue.id);
  const page = issuePage({
    issue,
    users: people || [],
    parent,
    children,
    dependencies: { blocks: [], blocked_by: [], relates_to: [] },
    history: [],
    historyAvailable: false,
    sprint,
  });
  page.complete = false;
  return page;
}

function freshIssue(projectId, issue, issues, people, sprint) {
  return {
    id: issue.id,
    projectId,
    baseUpdatedAt: issue.updated_at,
    raw: issue,
    page: pageFromSnapshot(issue, issues, people, sprint),
    pending: false,
    conflict: null,
    error: null,
  };
}

function applyRefresh(store, snapshots, extras) {
  const next = clone(store);
  next.people = extras && extras.people ? extras.people : next.people;
  next.labels = extras && extras.labels ? extras.labels : next.labels;
  for (const snapshot of snapshots || []) {
    const incoming = snapshot.project;
    const existing = next.projects[incoming.id];
    const record = existing || {
      id: incoming.id,
      key: incoming.key,
      name: incoming.name,
      enabled: true,
      saved: false,
      sprint: null,
      issues: {},
    };
    record.key = incoming.key;
    record.name = incoming.name;
    if (!record.enabled) {
      next.projects[incoming.id] = record;
      continue;
    }
    record.saved = true;
    record.sprint = snapshot.sprint || null;
    const kept = {};
    const serverIssues = snapshot.issues || [];
    for (const issue of serverIssues) {
      const prior = record.issues[issue.id];
      if (prior && (prior.pending || prior.conflict)) {
        kept[issue.id] = prior;
      } else {
        kept[issue.id] = freshIssue(
          incoming.id,
          issue,
          serverIssues,
          next.people,
          snapshot.sprint,
        );
      }
    }
    for (const prior of Object.values(record.issues || {})) {
      if ((prior.pending || prior.conflict) && !kept[prior.id]) {
        kept[prior.id] = prior;
      }
    }
    record.issues = kept;
    next.projects[incoming.id] = record;
  }
  return next;
}

function workView(store) {
  return projectList(store)
    .filter((project) => project.enabled)
    .map((project) => ({
      projectId: project.id,
      projectKey: project.key,
      projectName: project.name,
      saved: Boolean(project.saved),
      sprintName: project.sprint ? project.sprint.name : null,
      issues: Object.values(project.issues).map((issue) => ({
        id: issue.id,
        key: issue.page ? issue.page.key : issue.raw.key,
        title: issue.page ? issue.page.title : issue.raw.title,
        statusLabel: issue.page
          ? issue.page.statusLabel
          : statusLabel(issue.raw.status),
        pending: Boolean(issue.pending || issue.conflict),
      })),
    }));
}

function enqueue(store, item) {
  const next = clone(store);
  const issue = findIssue(next, item.issueId);
  if (!issue) {
    return next;
  }
  issue.pending = true;
  issue.error = null;
  next.queue.push({
    id: item.id || `${item.kind}-${item.issueId}-${next.queue.length}`,
    kind: item.kind,
    issueId: item.issueId,
    projectId: issue.projectId,
    method: item.method,
    path: item.path,
    body: item.body || null,
    baseUpdatedAt: item.baseUpdatedAt || issue.baseUpdatedAt,
    force: Boolean(item.force),
  });
  return next;
}

function choosePhone(store, issueId) {
  const next = clone(store);
  const issue = findIssue(next, issueId);
  if (!issue || !issue.conflict) {
    return next;
  }
  issue.conflict = null;
  issue.pending = true;
  for (const item of next.queue) {
    if (item.issueId === issueId) {
      item.force = true;
    }
  }
  return next;
}

function chooseServer(store, issueId, serverIssue, page) {
  const next = clone(store);
  const issue = findIssue(next, issueId);
  if (!issue) {
    return next;
  }
  next.queue = next.queue.filter((item) => item.issueId !== issueId);
  issue.raw = serverIssue;
  issue.baseUpdatedAt = serverIssue.updated_at;
  if (page) {
    issue.page = page;
  }
  issue.pending = false;
  issue.conflict = null;
  issue.error = null;
  return next;
}

function discardIssue(store, issueId) {
  const next = clone(store);
  next.queue = next.queue.filter((item) => item.issueId !== issueId);
  for (const project of Object.values(next.projects)) {
    delete project.issues[issueId];
  }
  return next;
}

function queueRecreate(store, issueId) {
  const next = clone(store);
  const issue = findIssue(next, issueId);
  if (!issue) {
    return next;
  }
  const raw = issue.raw;
  next.queue = next.queue.filter((item) => item.issueId !== issueId);
  next.queue.push({
    id: `create-${issueId}`,
    kind: "create",
    issueId,
    projectId: issue.projectId,
    method: "POST",
    path: `/api/v1/projects/${issue.projectId}/issues`,
    body: {
      type: raw.type,
      title: raw.title,
      description: raw.description || "",
      status: raw.status,
      priority: raw.priority,
      assignee_id: raw.assignee_id,
      sprint_id: raw.sprint_id,
      estimate_minutes: raw.estimate_minutes,
      remaining_minutes: raw.remaining_minutes,
      start_at: raw.start_at,
      due_at: raw.due_at,
      labels: raw.labels || [],
    },
    baseUpdatedAt: null,
    force: true,
  });
  issue.conflict = null;
  issue.pending = true;
  issue.error = null;
  return next;
}

function dropProject(store, projectId) {
  const next = clone(store);
  const project = next.projects[projectId];
  if (!project) {
    return next;
  }
  next.queue = next.queue.filter((item) => item.projectId !== projectId);
  project.enabled = false;
  project.saved = false;
  project.sprint = null;
  project.issues = {};
  return next;
}

function enableProject(store, projectId) {
  const next = clone(store);
  const project = next.projects[projectId];
  if (!project) {
    return next;
  }
  project.enabled = true;
  return next;
}

function markConflict(store, issueId, conflict) {
  const next = clone(store);
  const issue = findIssue(next, issueId);
  if (!issue) {
    return next;
  }
  issue.conflict = conflict;
  issue.pending = true;
  return next;
}

function markError(store, issueId, message) {
  const next = clone(store);
  const issue = findIssue(next, issueId);
  if (!issue) {
    return next;
  }
  issue.error = message;
  issue.pending = true;
  return next;
}

function noteUploaded(store, item, saved) {
  const next = clone(store);
  next.queue = next.queue.filter((entry) => entry.id !== item.id);
  if (item.kind === "delete") {
    return discardIssue(next, item.issueId);
  }
  const issue = findIssue(next, item.issueId);
  if (item.kind === "create" && saved && issue) {
    const project = next.projects[issue.projectId];
    delete project.issues[item.issueId];
    project.issues[saved.id] = freshIssue(
      issue.projectId,
      saved,
      [saved],
      next.people,
      project.sprint,
    );
    return next;
  }
  if (issue && saved) {
    issue.raw = saved;
    issue.baseUpdatedAt = saved.updated_at;
    issue.page = pageFromSnapshot(saved, [saved], next.people, null);
    issue.page.complete = false;
  }
  if (issue) {
    issue.pending = next.queue.some((entry) => entry.issueId === item.issueId);
    if (!issue.pending) {
      issue.error = null;
      issue.conflict = null;
    }
  }
  return next;
}

function rememberDetail(store, issueId, raw, page) {
  const next = clone(store);
  const issue = findIssue(next, issueId);
  if (!issue || issue.pending || issue.conflict) {
    return next;
  }
  issue.raw = raw;
  issue.baseUpdatedAt = raw.updated_at;
  issue.page = page;
  issue.page.complete = true;
  return next;
}

function localIssueId(store) {
  let lowest = 0;
  for (const project of Object.values(store.projects || {})) {
    for (const id of Object.keys(project.issues || {})) {
      lowest = Math.min(lowest, Number(id));
    }
  }
  return lowest - 1;
}

function queueCreate(store, draft) {
  const next = clone(store);
  const project = next.projects[draft.projectId];
  if (!project || !project.enabled) {
    return { store: next, error: "Choose a saved project." };
  }
  const title = (draft.title || "").trim();
  if (!title) {
    return { store: next, error: "Enter a title." };
  }
  const localId = localIssueId(next);
  const raw = {
    id: localId,
    key: "",
    project_id: project.id,
    title,
    type: draft.type || "story",
    description: draft.description || "",
    status: draft.status || "todo",
    priority: draft.priority || "p4",
    parent_id: draft.parent_id || null,
    sprint_id: draft.sprint_id || null,
    reporter_id: null,
    assignee_id: draft.assignee_id || null,
    estimate_minutes: draft.estimate_minutes ?? null,
    remaining_minutes: draft.remaining_minutes ?? null,
    start_at: draft.start_at || null,
    due_at: draft.due_at || null,
    labels: draft.labels || [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    rollup: null,
  };
  const record = freshIssue(project.id, raw, Object.values(project.issues).map((item) => item.raw).concat(raw), next.people, project.sprint);
  record.pending = true;
  project.issues[localId] = record;
  next.queue.push({
    id: `create-${localId}`,
    kind: "create",
    issueId: localId,
    projectId: project.id,
    method: "POST",
    path: `/api/v1/projects/${project.id}/issues`,
    body: {
      type: raw.type,
      title: raw.title,
      description: raw.description,
      status: raw.status,
      priority: raw.priority,
      parent_id: raw.parent_id,
      sprint_id: raw.sprint_id,
      assignee_id: raw.assignee_id,
      estimate_minutes: raw.estimate_minutes,
      remaining_minutes: raw.remaining_minutes,
      start_at: raw.start_at,
      due_at: raw.due_at,
      labels: raw.labels,
    },
    baseUpdatedAt: null,
    force: true,
  });
  return { store: next, error: null, issueId: localId };
}

module.exports = {
  NOT_ON_SERVER,
  applyRefresh,
  choosePhone,
  chooseServer,
  discardIssue,
  dropProject,
  emptyStore,
  enableProject,
  enqueue,
  findIssue,
  hasWaiting,
  markConflict,
  markError,
  noteUploaded,
  queueCreate,
  queueRecreate,
  rememberDetail,
  storeKey,
  workView,
};
