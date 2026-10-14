const assert = require("node:assert/strict");
const test = require("node:test");

const {
  applyRefresh,
  choosePhone,
  chooseServer,
  discardIssue,
  dropProject,
  emptyStore,
  enqueue,
  hasWaiting,
  queueRecreate,
  workView,
} = require("./offline");
const { uploadQueue } = require("./sync");

function snapshot() {
  return {
    project: { id: 3, key: "KEEL", name: "Keel" },
    sprint: { id: 7, name: "This month", state: "active" },
    issues: [
      {
        id: 9,
        key: "KEEL-9",
        project_id: 3,
        title: "Paint",
        type: "story",
        status: "todo",
        priority: "p4",
        assignee_id: null,
        reporter_id: null,
        labels: [],
        parent_id: null,
        sprint_id: 7,
        description: "",
        estimate_minutes: null,
        remaining_minutes: null,
        start_at: null,
        due_at: null,
        created_at: "2026-10-01T00:00:00",
        updated_at: "2026-10-01T00:00:00",
        rollup: null,
      },
    ],
  };
}

test("a new project starts saved and enabled", () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const view = workView(store);
  assert.equal(view.length, 1);
  assert.equal(view[0].sprintName, "This month");
  assert.equal(view[0].issues[0].key, "KEEL-9");
  assert.equal(view[0].issues[0].pending, false);
});

test("refresh leaves a waiting issue alone", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = enqueue(store, {
    kind: "patch",
    issueId: 9,
    method: "PATCH",
    path: "/api/v1/issues/9",
    body: { title: "Phone title" },
  });
  const changed = snapshot();
  changed.issues[0] = { ...changed.issues[0], title: "Server title", updated_at: "2026-10-02T00:00:00" };
  store = applyRefresh(store, [changed], { people: [], labels: [] });
  assert.equal(store.projects[3].issues[9].raw.title, "Paint");
  assert.equal(workView(store)[0].issues[0].pending, true);
});

test("turning a project off drops its waiting changes", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = enqueue(store, {
    kind: "patch",
    issueId: 9,
    method: "PATCH",
    path: "/api/v1/issues/9",
    body: { title: "Phone title" },
  });
  assert.equal(hasWaiting(store, 3), true);
  store = dropProject(store, 3);
  assert.equal(hasWaiting(store, 3), false);
  assert.equal(workView(store).length, 0);
  assert.equal(store.projects[3].enabled, false);
});

test("a quiet change uploads and a disagreement waits", async () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = enqueue(store, {
    id: "quiet",
    kind: "patch",
    issueId: 9,
    method: "PATCH",
    path: "/api/v1/issues/9",
    body: { title: "Quiet" },
    baseUpdatedAt: "2026-10-01T00:00:00",
  });
  const quiet = await uploadQueue(store, {
    async read() {
      return snapshot().issues[0];
    },
    async send() {
      return { ...snapshot().issues[0], title: "Quiet", updated_at: "2026-10-03T00:00:00" };
    },
  });
  assert.equal(quiet.queue.length, 0);
  assert.equal(quiet.projects[3].issues[9].pending, false);

  store = enqueue(applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] }), {
    id: "loud",
    kind: "patch",
    issueId: 9,
    method: "PATCH",
    path: "/api/v1/issues/9",
    body: { title: "Loud" },
    baseUpdatedAt: "2026-10-01T00:00:00",
  });
  const held = await uploadQueue(store, {
    async read() {
      return { ...snapshot().issues[0], title: "Other", updated_at: "2026-10-04T00:00:00" };
    },
    async send() {
      throw new Error("should not upload");
    },
  });
  assert.equal(held.projects[3].issues[9].conflict.kind, "changed");
  assert.equal(held.queue.length, 1);

  const forced = choosePhone(held, 9);
  assert.equal(forced.projects[3].issues[9].conflict, null);
  assert.equal(forced.queue[0].force, true);
  const kept = chooseServer(held, 9, held.projects[3].issues[9].conflict.server, null);
  assert.equal(kept.queue.length, 0);
  assert.equal(kept.projects[3].issues[9].raw.title, "Other");
});

test("a deleted issue can be discarded or filed again", async () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = enqueue(store, {
    id: "gone",
    kind: "patch",
    issueId: 9,
    method: "PATCH",
    path: "/api/v1/issues/9",
    body: { title: "Still here" },
  });
  const missing = new Error("missing");
  missing.status = 404;
  const held = await uploadQueue(store, {
    async read() {
      throw missing;
    },
    async send() {
      throw new Error("should not upload");
    },
  });
  assert.equal(held.projects[3].issues[9].conflict.kind, "deleted");
  const dropped = discardIssue(held, 9);
  assert.equal(dropped.projects[3].issues[9], undefined);
  const again = queueRecreate(held, 9);
  assert.equal(again.queue[0].kind, "create");
  assert.equal(again.queue[0].path, "/api/v1/projects/3/issues");
});
