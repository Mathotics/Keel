const { commentView, formatMinutes, formatMoney, formatWhen, issuePage, priorityLabel, typeLabel } = require("./issue");
const { cadenceSummary } = require("./series");
const { statusLabel } = require("./work");

const NOT_ON_SERVER = "Not on the server yet.";

function newClientKey() {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") {
    return cryptoApi.randomUUID().replace(/-/g, "");
  }
  let key = "";
  for (let index = 0; index < 32; index += 1) {
    key += Math.floor(Math.random() * 16).toString(16);
  }
  return key;
}

function providedClientKey(value) {
  const cleaned = String(value || "").trim();
  if (/^[A-Za-z0-9_-]{16,64}$/.test(cleaned)) {
    return cleaned;
  }
  return null;
}

function issueCreateBody(raw, clientKey) {
  return {
    type: raw.type,
    title: raw.title,
    description: raw.description || "",
    definition_of_done: raw.definition_of_done || "",
    ...(raw.location ? { location: raw.location } : {}),
    status: raw.status,
    priority: raw.priority,
    parent_id: raw.parent_id || null,
    sprint_id: raw.sprint_id || null,
    assignee_id: raw.assignee_id || null,
    estimate_minutes: raw.estimate_minutes ?? null,
    remaining_minutes: raw.remaining_minutes ?? null,
    planned_value_cents: raw.planned_value_cents ?? null,
    earned_value_cents: raw.earned_value_cents ?? null,
    actual_cost_cents: raw.actual_cost_cents ?? null,
    start_at: raw.start_at || null,
    due_at: raw.due_at || null,
    labels: raw.labels || [],
    client_key: clientKey,
  };
}

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

function pageFromSnapshot(issue, issues, people, sprint, currency) {
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
    currency,
  });
  page.complete = false;
  return page;
}

function freshIssue(projectId, issue, issues, people, sprint, currency) {
  return {
    id: issue.id,
    projectId,
    baseUpdatedAt: issue.updated_at,
    raw: issue,
    page: pageFromSnapshot(issue, issues, people, sprint, currency),
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
    record.currency = incoming.currency || record.currency || "USD";
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
          record.currency,
        );
        if (prior && prior.raw && prior.raw.client_key) {
          fresh.raw.client_key = prior.raw.client_key;
        }
        if (prior && prior.page && prior.page.comments) {
          fresh.page.comments = prior.page.comments.filter((comment) => !comment.pending);
        }
        kept[issue.id] = fresh;
      }
    }
    for (const prior of Object.values(record.issues || {})) {
      if (!kept[prior.id]) {
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
  const waiting = (store.queue || []).find(
    (item) => item.issueId === issueId && item.kind === "create" && item.body,
  );
  const clientKey = providedClientKey(raw.client_key)
    || providedClientKey(waiting && waiting.body.client_key)
    || newClientKey();
  raw.client_key = clientKey;
  next.queue = next.queue.filter((item) => item.issueId !== issueId);
  next.queue.push({
    id: `create-${issueId}`,
    kind: "create",
    issueId,
    projectId: issue.projectId,
    method: "POST",
    path: `/api/v1/projects/${issue.projectId}/issues`,
    body: issueCreateBody(raw, clientKey),
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
  project.series = {};
  project.seriesLoaded = false;
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

function markSeriesError(store, projectId, seriesId, message) {
  const next = clone(store);
  const project = next.projects[projectId];
  const record = project && project.series && project.series[seriesId];
  if (!record) {
    return next;
  }
  record.error = message;
  record.pending = true;
  return next;
}

function noteUploaded(store, item, saved) {
  const next = clone(store);
  next.queue = next.queue.filter((entry) => entry.id !== item.id);
  if (item.kind === "delete") {
    return discardIssue(next, item.issueId);
  }
  if (item.kind === "series") {
    const project = next.projects[item.projectId];
    if (project) {
      if (!project.series) {
        project.series = {};
      }
      delete project.series[item.seriesId];
      if (saved && saved.id != null) {
        project.series[saved.id] = {
          id: saved.id,
          pending: false,
          error: null,
          raw: saved,
        };
      }
    }
    return next;
  }
  const issue = findIssue(next, item.issueId);
  if (item.kind === "create" && saved && issue) {
    const project = next.projects[issue.projectId];
    const comments = (issue.page && issue.page.comments) || [];
    delete project.issues[item.issueId];
    const filed = item.body && item.body.client_key
      ? { ...saved, client_key: item.body.client_key }
      : saved;
    const created = freshIssue(
      issue.projectId,
      filed,
      [filed],
      next.people,
      project.sprint,
      project.currency,
    );
    created.page.comments = comments;
    project.issues[filed.id] = created;
    for (const entry of next.queue) {
      if (entry.issueId === item.issueId) {
        entry.issueId = filed.id;
        if (entry.kind === "comment") {
          entry.path = `/api/v1/issues/${filed.id}/comments`;
        }
      }
    }
    created.pending = next.queue.some((entry) => entry.issueId === filed.id);
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
    issue.page = pageFromSnapshot(
      saved,
      [saved],
      next.people,
      null,
      next.projects[issue.projectId] && next.projects[issue.projectId].currency,
    );
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

function absorbIssues(store, projectId, issues) {
  const next = clone(store);
  const record = next.projects[projectId];
  if (!record || !record.enabled) {
    return next;
  }
  const incoming = new Set();
  const list = issues || [];
  for (const issue of list) {
    incoming.add(issue.id);
    const prior = record.issues[issue.id];
    if (prior && (prior.pending || prior.conflict)) {
      continue;
    }
    const fresh = freshIssue(record.id, issue, list, next.people, record.sprint, record.currency);
    if (prior && prior.raw && prior.raw.client_key) {
      fresh.raw.client_key = prior.raw.client_key;
    }
    if (issue.completed_at) {
      fresh.raw.completedOn = issue.completed_at;
    }
    if (prior && prior.page && prior.page.complete) {
      fresh.page = prior.page;
      fresh.page.complete = true;
    } else if (prior && prior.page && prior.page.comments) {
      fresh.page.comments = prior.page.comments.filter((comment) => !comment.pending);
    }
    record.issues[issue.id] = fresh;
  }
  for (const prior of Object.values(record.issues)) {
    if (Number(prior.id) > 0 && !incoming.has(prior.id) && !prior.pending && !prior.conflict) {
      delete record.issues[prior.id];
    }
  }
  record.saved = true;
  record.catalog = true;
  return next;
}

function rememberDetail(store, issueId, raw, page) {
  const next = clone(store);
  let issue = findIssue(next, issueId);
  if (issue && (issue.pending || issue.conflict)) {
    return next;
  }
  if (!issue) {
    const project = raw && next.projects[raw.project_id];
    if (!project) {
      return next;
    }
    issue = freshIssue(project.id, raw, [], next.people, project.sprint, project.currency);
    project.issues[issueId] = issue;
  }
  issue.raw = raw;
  issue.baseUpdatedAt = raw.updated_at;
  issue.page = page;
  issue.page.complete = true;
  return next;
}

function retainUpload(latest, before, uploaded) {
  const next = clone(latest);
  const stillQueued = new Set((uploaded.queue || []).map((item) => item.id));
  const finished = (before.queue || []).filter(
    (item) => item.kind === "create" && !stillQueued.has(item.id),
  );
  for (const item of finished) {
    const key = item.body && item.body.client_key;
    next.queue = (next.queue || []).filter((entry) => {
      if (entry.id === item.id) {
        return false;
      }
      return !(key && entry.kind === "create" && entry.body && entry.body.client_key === key);
    });
    const project = uploaded.projects && uploaded.projects[item.projectId];
    const home = next.projects && next.projects[item.projectId];
    if (!project || !home) {
      continue;
    }
    const created = Object.values(project.issues || {}).find(
      (issue) => key && issue.raw && issue.raw.client_key === key && Number(issue.id) > 0,
    );
    if (!created) {
      continue;
    }
    if (home.issues[item.issueId]) {
      delete home.issues[item.issueId];
    }
    if (!home.issues[created.id]) {
      home.issues[created.id] = created;
    }
  }
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

function reuseQueuedCreate(store, pending, draft, clientKey) {
  const next = clone(store);
  const queued = next.queue.find((item) => item.id === pending.id);
  const issue = findIssue(next, pending.issueId);
  const project = next.projects[draft.projectId];
  if (!queued || !issue || !project || !project.enabled) {
    return { store, error: "Choose a saved project." };
  }
  if (issue.projectId !== draft.projectId) {
    const from = next.projects[issue.projectId];
    if (from && from.issues) {
      delete from.issues[issue.id];
    }
    issue.projectId = draft.projectId;
    project.issues[issue.id] = issue;
  }
  Object.assign(issue.raw, {
    project_id: draft.projectId,
    title: (draft.title || "").trim(),
    type: draft.type || "story",
    description: draft.description || "",
    definition_of_done: draft.definition_of_done || "",
    location: draft.location || "",
    status: draft.status || "todo",
    priority: draft.priority || "p4",
    parent_id: draft.parent_id || null,
    sprint_id: draft.sprint_id || null,
    assignee_id: draft.assignee_id || null,
    estimate_minutes: draft.estimate_minutes ?? null,
    remaining_minutes: draft.remaining_minutes ?? null,
    planned_value_cents: draft.planned_value_cents ?? null,
    earned_value_cents: draft.earned_value_cents ?? null,
    actual_cost_cents: draft.actual_cost_cents ?? null,
    start_at: draft.start_at || null,
    due_at: draft.due_at || null,
    labels: draft.labels || [],
    client_key: clientKey,
    updated_at: new Date().toISOString(),
  });
  if (issue.page) {
    issue.page.title = issue.raw.title;
    issue.page.key = issue.page.key || "";
  }
  queued.projectId = draft.projectId;
  queued.path = `/api/v1/projects/${draft.projectId}/issues`;
  queued.body = issueCreateBody(issue.raw, clientKey);
  issue.pending = true;
  issue.error = null;
  return { store: next, error: null, issueId: issue.id };
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
  const clientKey = providedClientKey(draft.client_key) || newClientKey();
  const parentWaiting = draft.parent_id && (store.queue || []).some(
    (item) => item.issueId === draft.parent_id && item.kind === "delete",
  );
  if (parentWaiting) {
    return { store, error: "This issue is waiting to be deleted." };
  }
  const pending = (store.queue || []).find(
    (item) => item.kind === "create" && item.body && item.body.client_key === clientKey,
  );
  if (pending) {
    return reuseQueuedCreate(store, pending, draft, clientKey);
  }
  const localId = localIssueId(next);
  const raw = {
    id: localId,
    key: "",
    project_id: project.id,
    title,
    type: draft.type || "story",
    description: draft.description || "",
    definition_of_done: draft.definition_of_done || "",
    location: draft.location || "",
    status: draft.status || "todo",
    priority: draft.priority || "p4",
    parent_id: draft.parent_id || null,
    sprint_id: draft.sprint_id || null,
    reporter_id: null,
    assignee_id: draft.assignee_id || null,
    estimate_minutes: draft.estimate_minutes ?? null,
    remaining_minutes: draft.remaining_minutes ?? null,
    planned_value_cents: draft.planned_value_cents ?? null,
    earned_value_cents: draft.earned_value_cents ?? null,
    actual_cost_cents: draft.actual_cost_cents ?? null,
    start_at: draft.start_at || null,
    due_at: draft.due_at || null,
    labels: draft.labels || [],
    client_key: clientKey,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    rollup: null,
  };
  const record = freshIssue(project.id, raw, Object.values(project.issues).map((item) => item.raw).concat(raw), next.people, project.sprint, project.currency);
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
    body: issueCreateBody(raw, clientKey),
    baseUpdatedAt: null,
    force: true,
  });
  return { store: next, error: null, issueId: localId };
}

function findSeries(store, seriesId) {
  for (const project of Object.values(store.projects || {})) {
    if (project.series && project.series[seriesId]) {
      return project.series[seriesId];
    }
  }
  return null;
}

function localSeriesId(store) {
  let lowest = 0;
  for (const project of Object.values(store.projects || {})) {
    for (const id of Object.keys(project.series || {})) {
      lowest = Math.min(lowest, Number(id));
    }
  }
  return lowest - 1;
}

function seriesPostBody(body) {
  const items = (body.items || []).map((item) => {
    const copy = { ...item };
    delete copy.assignee;
    return copy;
  });
  const posted = {
    title: String(body.title || "").trim(),
    description: body.description || "",
    type: body.type || "story",
    priority: body.priority || "p4",
    spawn_mode: body.spawn_mode || "calendar",
    sprint_basis: body.sprint_basis || "due_on",
    freq: body.freq || "weekly",
    starts_on: body.starts_on,
    interval: body.interval || 1,
    weekdays: body.weekdays || [],
    month_day: body.month_day ?? null,
    nth_week: body.nth_week ?? null,
    month: body.month ?? null,
    ends_on: body.ends_on ?? null,
    occurrence_count: body.occurrence_count ?? null,
    look_ahead_n: body.look_ahead_n || 1,
    start_offset_days: body.start_offset_days ?? null,
    start_minute_of_day: body.start_minute_of_day ?? null,
    due_offset_days: body.due_offset_days ?? null,
    due_minute_of_day: body.due_minute_of_day ?? null,
    parent_id: body.parent_id ?? null,
    assignee_id: body.assignee_id ?? null,
    labels: body.labels || [],
    items,
  };
  if (body.seed_issue_id != null) {
    posted.seed_issue_id = body.seed_issue_id;
  }
  return posted;
}

function rawFromSeriesBody(id, projectId, body) {
  return {
    id,
    project_id: projectId,
    title: body.title,
    description: body.description,
    type: body.type,
    priority: body.priority,
    labels: body.labels,
    spawn_mode: body.spawn_mode,
    sprint_basis: body.sprint_basis,
    freq: body.freq,
    interval: body.interval,
    weekdays: (body.weekdays || []).join(","),
    month_day: body.month_day,
    nth_week: body.nth_week,
    month: body.month,
    starts_on: body.starts_on,
    ends_on: body.ends_on,
    occurrence_count: body.occurrence_count,
    look_ahead_n: body.look_ahead_n,
    start_offset_days: body.start_offset_days,
    start_minute_of_day: body.start_minute_of_day,
    due_offset_days: body.due_offset_days,
    due_minute_of_day: body.due_minute_of_day,
    parent_id: body.parent_id,
    assignee_id: body.assignee_id,
    state: "active",
    cadence_summary: cadenceSummary(body),
    items: body.items || [],
  };
}

function queueSeries(store, projectId, body) {
  const next = clone(store);
  const project = next.projects[projectId];
  if (!project || !project.enabled) {
    return { store: next, error: "Choose a saved project." };
  }
  const posted = seriesPostBody(body || {});
  if (!posted.title) {
    return { store: next, error: "A series needs a title." };
  }
  if (Number(posted.parent_id) < 0) {
    return { store: next, error: "That parent is not on the server yet." };
  }
  if (Number(posted.seed_issue_id) < 0) {
    return { store: next, error: "This issue is not on the server yet." };
  }
  const localId = localSeriesId(next);
  if (!project.series) {
    project.series = {};
  }
  project.series[localId] = {
    id: localId,
    pending: true,
    error: null,
    raw: rawFromSeriesBody(localId, project.id, posted),
  };
  next.queue.push({
    id: `series-${localId}`,
    kind: "series",
    seriesId: localId,
    projectId: project.id,
    method: "POST",
    path: `/api/v1/projects/${project.id}/series`,
    body: posted,
    baseUpdatedAt: null,
    force: true,
  });
  return { store: next, error: null, seriesId: localId };
}

function rememberSeries(store, projectId, list) {
  const next = clone(store);
  const project = next.projects[projectId];
  if (!project || !project.enabled) {
    return next;
  }
  const kept = {};
  for (const prior of Object.values(project.series || {})) {
    if (prior.pending || Number(prior.id) < 0) {
      kept[prior.id] = prior;
    }
  }
  for (const series of list || []) {
    if (!kept[series.id]) {
      kept[series.id] = {
        id: series.id,
        pending: false,
        error: null,
        raw: series,
      };
    }
  }
  project.series = kept;
  project.seriesLoaded = true;
  return next;
}

function savedSeries(store, projectId) {
  const project = store.projects && store.projects[projectId];
  if (!project || !project.enabled) {
    return null;
  }
  return Object.values(project.series || {})
    .map((record) => ({
      ...record.raw,
      pending: Boolean(record.pending),
      error: record.error || "",
    }))
    .sort((left, right) => String(left.title || "").localeCompare(String(right.title || "")));
}

function seriesKnown(store, projectId) {
  const project = store.projects && store.projects[projectId];
  return Boolean(project && project.seriesLoaded);
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
  issue.page = pageFromSnapshot(issue.raw, issues, people, sprint, project && project.currency);
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
  const pendingCreate = next.queue.find((item) => item.issueId === record.id && item.kind === "create");
  if (!pendingCreate) {
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
        prior: {},
        baseUpdatedAt: record.baseUpdatedAt,
        force: false,
      };
      next.queue.push(pendingUpdate);
    }
    if (!pendingUpdate.prior) {
      pendingUpdate.prior = {};
    }
    for (const key of Object.keys(changes)) {
      if (!Object.prototype.hasOwnProperty.call(pendingUpdate.prior, key)) {
        const previous = record.raw[key];
        if (previous && typeof previous === "object") {
          pendingUpdate.prior[key] = clone(previous);
        } else {
          pendingUpdate.prior[key] = previous === undefined ? null : previous;
        }
      }
    }
  }
  Object.assign(record.raw, changes);
  rewritePage(record, home, next.people, changes, options);
  record.pending = true;
  record.error = null;
  if (pendingCreate) {
    Object.assign(pendingCreate.body, changes);
    return { store: next, error: null };
  }
  const pendingUpdate = next.queue.find((item) => item.issueId === record.id && item.kind === "update");
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
    record.page = pageFromSnapshot(
      record.raw,
      [record.raw],
      next.people,
      null,
      next.projects[record.projectId] && next.projects[record.projectId].currency,
    );
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
  series: "Create schedule",
};

const QUEUE_FIELD = {
  type: "Type",
  title: "Title",
  description: "Description",
  definition_of_done: "Definition of Done",
  location: "Location",
  status: "Status",
  priority: "Priority",
  assignee_id: "Assignee",
  parent_id: "Parent",
  sprint_id: "Sprint",
  estimate_minutes: "Estimate",
  remaining_minutes: "Remaining",
  planned_value_cents: "Planned value",
  earned_value_cents: "Earned value",
  actual_cost_cents: "Actual cost",
  start_at: "Start",
  due_at: "Due",
  labels: "Labels",
};

// Long text left blank is noise in the queue summary.
const QUEUE_BLANK_HIDDEN = new Set(["description", "definition_of_done"]);

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

function queueValue(store, key, value, currency) {
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
  if (key === "planned_value_cents" || key === "earned_value_cents" || key === "actual_cost_cents") {
    return formatMoney(value, currency || "USD", "edit");
  }
  if (value == null || value === "") {
    return "Cleared";
  }
  return String(value);
}

function queueDetail(store, item) {
  if (item.kind === "series") {
    const body = item.body || {};
    return [body.title, body.starts_on].filter(Boolean).join(" · ");
  }
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
  const project = store.projects && store.projects[item.projectId];
  const currency = project && project.currency;
  return Object.keys(body)
    .filter((key) => !QUEUE_BLANK_HIDDEN.has(key) || body[key])
    .map((key) => `${QUEUE_FIELD[key] || key}: ${queueValue(store, key, body[key], currency)}`)
    .join("\n");
}

function unlinkChild(store, issueId) {
  for (const project of Object.values(store.projects || {})) {
    for (const issue of Object.values(project.issues || {})) {
      if (!issue.page || !issue.page.children) {
        continue;
      }
      issue.page.children = issue.page.children.filter((child) => child.id !== issueId);
    }
  }
}

// Fields a person can choose between when this phone and the server both changed.
const CONFLICT_FIELDS = [
  ["type", "Type"],
  ["title", "Title"],
  ["description", "Description"],
  ["definition_of_done", "Definition of Done"],
  ["location", "Location"],
  ["status", "Status"],
  ["priority", "Priority"],
  ["assignee_id", "Assignee"],
  ["parent_id", "Parent"],
  ["sprint_id", "Sprint"],
  ["estimate_minutes", "Estimate"],
  ["remaining_minutes", "Remaining"],
  ["planned_value_cents", "Planned value"],
  ["earned_value_cents", "Earned value"],
  ["actual_cost_cents", "Actual cost"],
  ["start_at", "Start"],
  ["due_at", "Due"],
  ["labels", "Labels"],
];

function conflictFieldValue(store, issue, key, value) {
  if (key === "type") {
    return value ? typeLabel(value) : "None";
  }
  if (key === "priority") {
    return value ? priorityLabel(value) : "None";
  }
  if (key === "estimate_minutes" || key === "remaining_minutes") {
    return formatMinutes(value);
  }
  if (key === "planned_value_cents" || key === "earned_value_cents" || key === "actual_cost_cents") {
    const project = issue && store.projects && store.projects[issue.projectId];
    return formatMoney(value, project && project.currency, "edit");
  }
  if (key === "start_at" || key === "due_at") {
    return formatWhen(value);
  }
  if (key === "labels") {
    const names = [...(value || [])].map(String).sort((left, right) => left.localeCompare(right));
    return names.length ? names.join(", ") : "None";
  }
  if (key === "assignee_id") {
    if (value == null) {
      return "Unassigned";
    }
    const person = (store.people || []).find((item) => item.id === value);
    return person ? person.display_name : `Person ${value}`;
  }
  if (key === "parent_id") {
    if (value == null) {
      return "No parent";
    }
    const name = queueIssueName(store, value);
    return name === "Issue" ? `Issue ${value}` : name;
  }
  if (key === "sprint_id") {
    if (value == null) {
      return "Unscheduled";
    }
    const named = queueSprint(store, value);
    if (named !== "A sprint") {
      return named;
    }
    if (issue && issue.raw && issue.raw.sprint_id === value && issue.page && issue.page.sprintName) {
      return issue.page.sprintName;
    }
    return `Sprint ${value}`;
  }
  const shown = queueValue(store, key, value);
  return shown === "Cleared" ? "None" : shown;
}

function savedFieldChanges(store, issue, server) {
  const phone = (issue && issue.raw) || {};
  const remote = server || {};
  const changes = [];
  for (const [key, label] of CONFLICT_FIELDS) {
    const phoneText = conflictFieldValue(store, issue, key, phone[key]);
    const serverText = conflictFieldValue(store, issue, key, remote[key]);
    if (phoneText === serverText) {
      continue;
    }
    changes.push({ field: label, phone: phoneText, server: serverText });
  }
  return changes;
}

function requestAlreadyOnServer(store, issue, server, body) {
  if (!issue || !server || savedFieldChanges(store, issue, server).length) {
    return false;
  }
  const payload = body && typeof body === "object" ? body : {};
  for (const key of Object.keys(payload)) {
    const phoneText = conflictFieldValue(store, issue, key, payload[key]);
    const serverText = conflictFieldValue(store, issue, key, server[key]);
    if (phoneText !== serverText) {
      return false;
    }
  }
  return true;
}

// The phone and the server already show the same saved fields. Sending the
// update would not change the ticket, so drop that request and keep the server
// copy (including its newer timestamp).
function acceptUnchangedServer(store, item, serverIssue) {
  const issue = findIssue(store, item && item.issueId);
  if (!issue || !serverIssue || !item) {
    return null;
  }
  if (item.kind !== "update" && item.kind !== "patch") {
    return null;
  }
  if (!requestAlreadyOnServer(store, issue, serverIssue, item.body)) {
    return null;
  }
  const next = clone(store);
  const record = findIssue(next, item.issueId);
  const clientKey = record.raw && record.raw.client_key;
  next.queue = next.queue.filter((entry) => entry.id !== item.id);
  record.raw = { ...record.raw, ...serverIssue };
  if (clientKey && record.raw.client_key == null) {
    record.raw.client_key = clientKey;
  }
  record.baseUpdatedAt = serverIssue.updated_at;
  const project = next.projects[record.projectId];
  if (record.page) {
    rewritePage(record, project, next.people, {}, {});
  }
  record.conflict = null;
  record.pending = next.queue.some((entry) => entry.issueId === item.issueId);
  if (!record.pending) {
    record.error = null;
  }
  return next;
}

function conflictView(store, issue) {
  if (!issue || !issue.conflict) {
    return null;
  }
  if (issue.conflict.kind === "deleted" || !issue.conflict.server) {
    return { kind: "deleted", changes: [] };
  }
  return { kind: "changed", changes: savedFieldChanges(store, issue, issue.conflict.server) };
}

function finishQueueEdit(issue, queue) {
  const mine = queue.filter((item) => item.issueId === issue.id);
  const structural = mine.some((item) => item.kind === "update" || item.kind === "delete");
  if (!structural && issue.conflict && issue.conflict.kind !== "deleted") {
    issue.conflict = null;
  }
  issue.pending = mine.length > 0 || Boolean(issue.conflict);
  if (!issue.pending) {
    issue.error = null;
  }
}

function dropQueueItem(store, itemId) {
  const item = (store.queue || []).find((entry) => entry.id === itemId);
  if (!item) {
    return { store, error: "That change is no longer waiting." };
  }
  if (item.kind === "series") {
    const next = clone(store);
    next.queue = next.queue.filter((entry) => entry.id !== item.id);
    const project = next.projects[item.projectId];
    if (project && project.series) {
      delete project.series[item.seriesId];
    }
    return { store: next, error: null };
  }
  if (item.kind === "create") {
    const issue = findIssue(store, item.issueId);
    const project = issue && store.projects[issue.projectId];
    const children = project ? knownChildren(project, item.issueId) : [];
    const listed = issue && issue.page && issue.page.children ? issue.page.children.length : 0;
    if (children.length || listed) {
      return { store, error: "Move or delete this issue's children first." };
    }
    const next = discardIssue(store, item.issueId);
    unlinkChild(next, item.issueId);
    return { store: next, error: null };
  }
  const next = clone(store);
  const record = findIssue(next, item.issueId);
  next.queue = next.queue.filter((entry) => entry.id !== item.id);
  if (item.kind === "update" && record && item.prior) {
    const changes = {};
    for (const key of Object.keys(item.prior)) {
      const previous = item.prior[key];
      const restored = previous && typeof previous === "object" ? clone(previous) : previous;
      record.raw[key] = restored;
      changes[key] = restored;
    }
    if (Object.keys(changes).length) {
      rewritePage(record, next.projects[record.projectId], next.people, changes, {});
    }
  }
  if (item.kind === "comment" && record && record.page) {
    record.page.comments = (record.page.comments || []).filter((comment) => comment.id !== item.commentId);
  }
  if (item.kind === "uncomment" && record && item.comment) {
    if (!record.page) {
      record.page = pageFromSnapshot(
      record.raw,
      [record.raw],
      next.people,
      null,
      next.projects[record.projectId] && next.projects[record.projectId].currency,
    );
    }
    const comments = record.page.comments || [];
    if (!comments.some((comment) => comment.id === item.comment.id)) {
      record.page.comments = [...comments, clone(item.comment)];
    }
  }
  if (record) {
    finishQueueEdit(record, next.queue);
  }
  return { store: next, error: null };
}

function presentQueue(store) {
  return (store.queue || []).map((item) => {
    if (item.kind === "series") {
      const record = findSeries(store, item.seriesId);
      return {
        id: item.id,
        issueId: null,
        project: queueProjectName(store, item.projectId),
        issue: (record && record.raw && record.raw.title) || (item.body && item.body.title) || "Schedule",
        action: QUEUE_ACTION.series,
        detail: queueDetail(store, item),
        held: false,
        conflict: null,
        error: (record && record.error) || "",
      };
    }
    const issue = findIssue(store, item.issueId);
    return {
      id: item.id,
      issueId: item.issueId,
      project: queueProjectName(store, item.projectId),
      issue: queueIssueName(store, item.issueId),
      action: QUEUE_ACTION[item.kind] || item.kind,
      detail: queueDetail(store, item),
      held: Boolean(issue && issue.conflict),
      conflict: conflictView(store, issue),
      error: issue && issue.error ? issue.error : "",
    };
  });
}

module.exports = {
  NOT_ON_SERVER,
  absorbIssues,
  acceptUnchangedServer,
  applyRefresh,
  choosePhone,
  chooseServer,
  conflictView,
  discardIssue,
  dropProject,
  dropQueueItem,
  forgetProject,
  emptyStore,
  enableProject,
  enqueue,
  findIssue,
  findSeries,
  hasWaiting,
  markConflict,
  markError,
  markSeriesError,
  newClientKey,
  noteUploaded,
  presentQueue,
  queueComment,
  queueCreate,
  queueDelete,
  queueRecreate,
  queueRemoveComment,
  queueSeries,
  queueUpdate,
  retainUpload,
  rememberDetail,
  rememberSeries,
  savedSeries,
  seriesKnown,
  renameProject,
  storeKey,
  workView,
};
