const { commentView, issuePage } = require("./issue");
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
        const fresh = freshIssue(
          incoming.id,
          issue,
          serverIssues,
          next.people,
          snapshot.sprint,
        );
        if (prior && prior.page && prior.page.comments) {
          fresh.page.comments = prior.page.comments.filter((comment) => !comment.pending);
        }
        kept[issue.id] = fresh;
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
        status: issue.raw ? issue.raw.status : "",
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

function renameProject(store, projectId, name) {
  const next = clone(store);
  const project = next.projects[projectId];
  if (!project) {
    return next;
  }
  project.name = name;
  return next;
}

function forgetProject(store, projectId) {
  const next = clone(store);
  delete next.projects[projectId];
  next.queue = next.queue.filter((item) => item.projectId !== projectId);
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
    const comments = (issue.page && issue.page.comments) || [];
    delete project.issues[item.issueId];
    const created = freshIssue(
      issue.projectId,
      saved,
      [saved],
      next.people,
      project.sprint,
    );
    created.page.comments = comments;
    project.issues[saved.id] = created;
    for (const entry of next.queue) {
      if (entry.issueId === item.issueId) {
        entry.issueId = saved.id;
        if (entry.kind === "comment") {
          entry.path = `/api/v1/issues/${saved.id}/comments`;
        }
      }
    }
    created.pending = next.queue.some((entry) => entry.issueId === saved.id);
    return next;
  }
  if (item.kind === "comment" || item.kind === "uncomment") {
    if (issue && issue.page) {
      const comments = issue.page.comments || [];
      if (item.kind === "uncomment") {
        issue.page.comments = comments.filter((comment) => comment.id !== item.commentId);
      } else if (saved) {
        issue.page.comments = comments.map((comment) =>
          comment.id === item.commentId
            ? commentView(
                {
                  id: saved.id,
                  author_id: saved.author_id,
                  author: comment.author,
                  body: saved.body,
                  created_at: saved.created_at,
                },
                next.people,
              )
            : comment,
        );
      }
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
  if (issue && saved) {
    const comments = issue.page && issue.page.comments;
    issue.raw = saved;
    issue.baseUpdatedAt = saved.updated_at;
    issue.page = pageFromSnapshot(saved, [saved], next.people, null);
    issue.page.complete = false;
    issue.page.comments = comments || [];
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
  if (raw.parent_id && next.queue.some((item) => item.issueId === raw.parent_id && item.kind === "delete")) {
    return { store, error: "This issue is waiting to be deleted." };
  }
  record.pending = true;
  project.issues[localId] = record;
  const parent = raw.parent_id ? findIssue(next, raw.parent_id) : null;
  if (parent && parent.page) {
    const children = parent.page.children || [];
    if (!children.some((item) => item.id === localId)) {
      children.push({
        id: localId,
        key: "",
        title: raw.title,
        statusLabel: statusLabel(raw.status),
      });
      parent.page.children = children;
    }
  }
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

function waitingToDelete(store, issueId) {
  return (store.queue || []).some((item) => item.issueId === issueId && item.kind === "delete");
}

function leavesActiveSprint(issue, changes, project, online) {
  if (!Object.prototype.hasOwnProperty.call(changes, "sprint_id")) {
    return null;
  }
  const nextSprint = changes.sprint_id ?? null;
  const currentSprint = issue.raw.sprint_id ?? null;
  const activeSprint = project && project.sprint ? project.sprint.id : null;
  if (nextSprint !== currentSprint && nextSprint !== activeSprint && !online) {
    return "Moving an issue off this sprint needs a connection.";
  }
  return null;
}

function rewritePage(issue, project, people, changes, options) {
  const previous = issue.page;
  const issues = Object.values(project.issues).map((item) => item.raw);
  if (options.parent && !issues.some((item) => item.id === options.parent.id)) {
    issues.push(options.parent);
  }
  let sprint = null;
  if (issue.raw.sprint_id && project.sprint && project.sprint.id === issue.raw.sprint_id) {
    sprint = project.sprint;
  } else if (options.sprint && options.sprint.id === issue.raw.sprint_id) {
    sprint = options.sprint;
  }
  issue.page = pageFromSnapshot(issue.raw, issues, people, sprint);
  if (!previous) {
    return;
  }
  issue.page.complete = previous.complete;
  issue.page.comments = previous.comments || [];
  issue.page.history = previous.history;
  issue.page.historyAvailable = previous.historyAvailable;
  issue.page.blocks = previous.blocks;
  issue.page.blockedBy = previous.blockedBy;
  issue.page.relatesTo = previous.relatesTo;
  issue.page.rollup = previous.rollup;
  if (!Object.prototype.hasOwnProperty.call(changes, "parent_id") && previous.parent) {
    issue.page.parent = previous.parent;
  }
  if (!Object.prototype.hasOwnProperty.call(changes, "sprint_id") && !sprint) {
    issue.page.sprintName = previous.sprintName;
  }
  const merged = [...(previous.children || [])];
  for (const child of issue.page.children || []) {
    if (!merged.some((item) => item.id === child.id)) {
      merged.push(child);
    }
  }
  issue.page.children = merged;
}

function queueUpdate(store, issueId, changes, options = {}) {
  if (!changes || !Object.keys(changes).length) {
    return { store, error: null };
  }
  const issue = findIssue(store, issueId);
  if (!issue) {
    return { store, error: "That issue is not on this phone." };
  }
  if (waitingToDelete(store, issue.id)) {
    return { store, error: "This issue is waiting to be deleted." };
  }
  const project = store.projects[issue.projectId];
  const blocked = leavesActiveSprint(issue, changes, project, Boolean(options.online));
  if (blocked) {
    return { store, error: blocked };
  }
  const next = clone(store);
  const record = findIssue(next, issueId);
  const home = next.projects[record.projectId];
  Object.assign(record.raw, changes);
  rewritePage(record, home, next.people, changes, options);
  record.pending = true;
  record.error = null;
  const pendingCreate = next.queue.find((item) => item.issueId === record.id && item.kind === "create");
  if (pendingCreate) {
    Object.assign(pendingCreate.body, changes);
    return { store: next, error: null };
  }
  let pendingUpdate = next.queue.find((item) => item.issueId === record.id && item.kind === "update");
  if (!pendingUpdate) {
    pendingUpdate = {
      id: `update-${record.id}`,
      kind: "update",
      issueId: record.id,
      projectId: record.projectId,
      method: "PATCH",
      path: `/api/v1/issues/${record.id}`,
      body: {},
      baseUpdatedAt: record.baseUpdatedAt,
      force: false,
    };
    next.queue.push(pendingUpdate);
  }
  Object.assign(pendingUpdate.body, changes);
  return { store: next, error: null };
}

function knownChildren(project, issueId) {
  return Object.values(project.issues || {}).filter(
    (item) => item.raw && item.raw.parent_id === issueId && item.id !== issueId,
  );
}

function queueDelete(store, issueId) {
  const issue = findIssue(store, issueId);
  if (!issue) {
    return { store, error: "That issue is not on this phone." };
  }
  const project = store.projects[issue.projectId];
  const children = knownChildren(project, issue.id);
  const listed = issue.page && issue.page.children ? issue.page.children.length : 0;
  if (children.length || listed) {
    return { store, error: "Move or delete this issue's children first." };
  }
  if (issue.id < 0) {
    return { store: discardIssue(store, issueId), error: null };
  }
  const next = clone(store);
  const record = findIssue(next, issueId);
  const force = next.queue.some((item) => item.issueId === record.id && item.force);
  next.queue = next.queue.filter((item) => item.issueId !== record.id);
  next.queue.push({
    id: `delete-${record.id}`,
    kind: "delete",
    issueId: record.id,
    projectId: record.projectId,
    method: "DELETE",
    path: `/api/v1/issues/${record.id}`,
    body: null,
    baseUpdatedAt: record.baseUpdatedAt,
    force,
  });
  record.pending = true;
  record.error = null;
  return { store: next, error: null };
}

function localCommentId(store) {
  let lowest = 0;
  for (const project of Object.values(store.projects || {})) {
    for (const issue of Object.values(project.issues || {})) {
      for (const comment of (issue.page && issue.page.comments) || []) {
        lowest = Math.min(lowest, Number(comment.id));
      }
    }
  }
  return lowest - 1;
}

function queueComment(store, issueId, text, authorName) {
  const body = String(text || "").trim();
  if (!body) {
    return { store, error: "A comment needs a body." };
  }
  const issue = findIssue(store, issueId);
  if (!issue) {
    return { store, error: "That issue is not on this phone." };
  }
  if (waitingToDelete(store, issue.id)) {
    return { store, error: "This issue is waiting to be deleted." };
  }
  const next = clone(store);
  const record = findIssue(next, issueId);
  const localId = localCommentId(next);
  const comment = commentView(
    {
      id: localId,
      author: authorName || "Someone",
      body,
      created_at: new Date().toISOString(),
      pending: true,
    },
    next.people,
  );
  if (!record.page) {
    record.page = pageFromSnapshot(record.raw, [record.raw], next.people, null);
  }
  record.page.comments = [...(record.page.comments || []), comment];
  record.pending = true;
  record.error = null;
  next.queue.push({
    id: `comment-${localId}`,
    kind: "comment",
    issueId: record.id,
    commentId: localId,
    projectId: record.projectId,
    method: "POST",
    path: `/api/v1/issues/${record.id}/comments`,
    body: { body },
    baseUpdatedAt: null,
    force: true,
  });
  return { store: next, error: null, commentId: localId };
}

function queueRemoveComment(store, issueId, commentId) {
  const issue = findIssue(store, issueId);
  if (!issue || !issue.page) {
    return { store, error: "That issue is not on this phone." };
  }
  const target = (issue.page.comments || []).find((comment) => comment.id === commentId);
  if (!target) {
    return { store, error: "That comment is not on this phone." };
  }
  const next = clone(store);
  const record = findIssue(next, issueId);
  record.page.comments = (record.page.comments || []).filter((comment) => comment.id !== commentId);
  if (commentId < 0 || target.pending) {
    next.queue = next.queue.filter((item) => item.commentId !== commentId);
    record.pending = next.queue.some((item) => item.issueId === record.id);
    if (!record.pending) {
      record.error = null;
    }
    return { store: next, error: null };
  }
  next.queue.push({
    id: `uncomment-${commentId}`,
    kind: "uncomment",
    issueId: record.id,
    commentId,
    comment: target,
    projectId: record.projectId,
    method: "DELETE",
    path: `/api/v1/comments/${commentId}`,
    body: null,
    baseUpdatedAt: record.baseUpdatedAt,
    force: true,
  });
  record.pending = true;
  record.error = null;
  return { store: next, error: null };
}

const QUEUE_ACTION = {
  create: "Create",
  update: "Update",
  delete: "Delete",
  comment: "Comment",
  uncomment: "Remove comment",
};

const QUEUE_FIELD = {
  type: "Type",
  title: "Title",
  description: "Description",
  status: "Status",
  priority: "Priority",
  assignee_id: "Assignee",
  parent_id: "Parent",
  sprint_id: "Sprint",
  estimate_minutes: "Estimate",
  remaining_minutes: "Remaining",
  start_at: "Start",
  due_at: "Due",
  labels: "Labels",
};

function queueIssueName(store, issueId) {
  const issue = findIssue(store, issueId);
  if (!issue || !issue.raw) {
    return "Issue";
  }
  const title = issue.raw.title || "Untitled";
  return issue.raw.key ? `${issue.raw.key} ${title}` : title;
}

function queueProjectName(store, projectId) {
  const project = store.projects && store.projects[projectId];
  if (!project) {
    return "";
  }
  return project.key ? `${project.key} · ${project.name}` : project.name || "";
}

function queuePerson(store, personId) {
  if (personId == null) {
    return "Unassigned";
  }
  const person = (store.people || []).find((item) => item.id === personId);
  return person ? person.display_name : "Someone";
}

function queueSprint(store, sprintId) {
  if (sprintId == null) {
    return "Unscheduled";
  }
  for (const project of Object.values(store.projects || {})) {
    if (project.sprint && project.sprint.id === sprintId) {
      return project.sprint.name;
    }
  }
  return "A sprint";
}

function queueValue(store, key, value) {
  if (key === "status") {
    return statusLabel(value);
  }
  if (key === "assignee_id") {
    return queuePerson(store, value);
  }
  if (key === "parent_id") {
    return value == null ? "No parent" : queueIssueName(store, value);
  }
  if (key === "sprint_id") {
    return queueSprint(store, value);
  }
  if (key === "labels") {
    return (value || []).length ? value.join(", ") : "None";
  }
  if (key === "estimate_minutes" || key === "remaining_minutes") {
    return value == null ? "None" : `${value}m`;
  }
  if (value == null || value === "") {
    return "Cleared";
  }
  return String(value);
}

function queueDetail(store, item) {
  if (item.kind === "comment") {
    return item.body && item.body.body ? item.body.body : "";
  }
  if (item.kind === "uncomment") {
    return item.comment && item.comment.body ? item.comment.body : "";
  }
  if (item.kind === "delete") {
    return "This issue will be deleted on the server.";
  }
  const body = item.body || {};
  return Object.keys(body)
    .filter((key) => key !== "description" || body.description)
    .map((key) => `${QUEUE_FIELD[key] || key}: ${queueValue(store, key, body[key])}`)
    .join("\n");
}

function presentQueue(store) {
  return (store.queue || []).map((item) => {
    const issue = findIssue(store, item.issueId);
    return {
      id: item.id,
      issueId: item.issueId,
      project: queueProjectName(store, item.projectId),
      issue: queueIssueName(store, item.issueId),
      action: QUEUE_ACTION[item.kind] || item.kind,
      detail: queueDetail(store, item),
      held: Boolean(issue && issue.conflict),
      error: issue && issue.error ? issue.error : "",
    };
  });
}

module.exports = {
  NOT_ON_SERVER,
  applyRefresh,
  choosePhone,
  chooseServer,
  discardIssue,
  dropProject,
  forgetProject,
  emptyStore,
  enableProject,
  enqueue,
  findIssue,
  hasWaiting,
  markConflict,
  markError,
  noteUploaded,
  presentQueue,
  queueComment,
  queueCreate,
  queueDelete,
  queueRecreate,
  queueRemoveComment,
  queueUpdate,
  rememberDetail,
  renameProject,
  storeKey,
  workView,
};
