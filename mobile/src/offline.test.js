const assert = require("node:assert/strict");
const test = require("node:test");

const {
  absorbIssues,
  applyRefresh,
  choosePhone,
  chooseServer,
  discardIssue,
  dropProject,
  dropQueueItem,
  emptyStore,
  forgetProject,
  enqueue,
  hasWaiting,
  markConflict,
  queueComment,
  queueCreate,
  queueDelete,
  queueRecreate,
  queueRemoveComment,
  queueUpdate,
  presentQueue,
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

test("a sprint refresh keeps issues saved outside that sprint", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store.projects[3].issues[15] = {
    id: 15,
    projectId: 3,
    raw: { id: 15, key: "KEEL-15", title: "Later", sprint_id: null, status: "todo" },
    page: { key: "KEEL-15", title: "Later" },
    pending: false,
    conflict: null,
  };
  store = applyRefresh(store, [snapshot()], { people: [], labels: [] });
  assert.equal(store.projects[3].issues[15].raw.title, "Later");
  assert.equal(store.projects[3].issues[9].raw.title, "Paint");
});

test("a full issue list replaces the saved copy and keeps a waiting edit", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = enqueue(store, {
    kind: "patch",
    issueId: 9,
    method: "PATCH",
    path: "/api/v1/issues/9",
    body: { title: "Phone title" },
  });
  store = absorbIssues(store, 3, [
    { ...snapshot().issues[0], title: "Server title" },
    {
      id: 15,
      key: "KEEL-15",
      title: "Backlog",
      status: "todo",
      sprint_id: null,
      project_id: 3,
      updated_at: "2026-10-02T00:00:00",
    },
  ]);
  assert.equal(store.projects[3].catalog, true);
  assert.equal(store.projects[3].issues[9].raw.title, "Paint");
  assert.equal(store.projects[3].issues[15].raw.title, "Backlog");
});

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

test("forgetting a deleted project removes it and its waiting changes", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = enqueue(store, {
    kind: "patch",
    issueId: 9,
    method: "PATCH",
    path: "/api/v1/issues/9",
    body: { title: "Phone title" },
  });
  store = forgetProject(store, 3);
  assert.equal(store.projects[3], undefined);
  assert.equal(store.queue.length, 0);
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

test("edits to a saved issue wait as one patch", async () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const updated = queueUpdate(store, 9, { title: "Boat" }, { online: false });
  assert.equal(updated.error, null);
  assert.equal(updated.store.queue[0].method, "PATCH");
  const again = queueUpdate(updated.store, 9, { status: "done" }, { online: false });
  assert.equal(again.store.queue.length, 1);
  assert.deepEqual(again.store.queue[0].body, { title: "Boat", status: "done" });
  assert.equal(again.store.projects[3].issues[9].raw.title, "Boat");
  assert.equal(workView(again.store)[0].issues[0].pending, true);
  const uploaded = await uploadQueue(again.store, {
    async read() {
      return snapshot().issues[0];
    },
    async send(method, path, body) {
      assert.equal(method, "PATCH");
      assert.equal(path, "/api/v1/issues/9");
      return { ...snapshot().issues[0], ...body, updated_at: "2026-10-03T00:00:00" };
    },
  });
  assert.equal(uploaded.queue.length, 0);
  assert.equal(uploaded.projects[3].issues[9].raw.title, "Boat");
  assert.equal(uploaded.projects[3].issues[9].pending, false);
});

test("moving off the active sprint waits for a connection", () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const moved = queueUpdate(store, 9, { sprint_id: null }, { online: false });
  assert.match(moved.error, /connection/);
  assert.equal(moved.store.queue.length, 0);
  const allowed = queueUpdate(store, 9, { sprint_id: 8 }, { online: true, sprint: { id: 8, name: "Next" } });
  assert.equal(allowed.error, null);
  assert.equal(allowed.store.projects[3].issues[9].raw.sprint_id, 8);
  assert.equal(allowed.store.projects[3].issues[9].page.sprintName, "Next");
});

test("a child stays under its parent until that issue is on the server", () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const child = queueCreate(store, {
    projectId: 3,
    title: "Chip",
    type: "subtask",
    parent_id: 9,
    sprint_id: 7,
  });
  assert.equal(child.error, null);
  assert.equal(
    child.store.projects[3].issues[9].page.children.some((item) => item.title === "Chip"),
    true,
  );
  const removed = queueDelete(child.store, 9);
  assert.match(removed.error, /children/);
});

test("a new issue can be changed and dropped before the server sees it", () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const filed = queueCreate(store, { projectId: 3, title: "Paint", type: "story", sprint_id: 7 });
  const updated = queueUpdate(filed.store, filed.issueId, { title: "Boat" }, { online: false });
  assert.equal(updated.store.queue.length, 1);
  assert.equal(updated.store.queue[0].kind, "create");
  assert.equal(updated.store.queue[0].body.title, "Boat");
  const removed = queueDelete(updated.store, filed.issueId);
  assert.equal(removed.error, null);
  assert.equal(removed.store.queue.length, 0);
  assert.equal(workView(removed.store)[0].issues.length, 1);
});

test("delete waits until the server accepts it", async () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const removed = queueDelete(store, 9);
  assert.equal(removed.error, null);
  assert.equal(removed.store.queue[0].method, "DELETE");
  assert.equal(workView(removed.store)[0].issues[0].pending, true);
  const uploaded = await uploadQueue(removed.store, {
    async read() {
      return snapshot().issues[0];
    },
    async send(method) {
      assert.equal(method, "DELETE");
      return null;
    },
  });
  assert.equal(workView(uploaded)[0].issues.length, 0);
});

test("a delete the server already applied is finished", async () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const removed = queueDelete(store, 9);
  const missing = new Error("missing");
  missing.status = 404;
  const uploaded = await uploadQueue(removed.store, {
    async read() {
      throw missing;
    },
    async send() {
      throw new Error("should not upload");
    },
  });
  assert.equal(uploaded.projects[3].issues[9], undefined);
  assert.equal(uploaded.queue.length, 0);
});

test("a comment waits with its issue until the server accepts it", async () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  assert.equal(queueComment(store, 9, "   ", "Cursor").error, "A comment needs a body.");
  const added = queueComment(store, 9, "  Hello  ", "Cursor");
  assert.equal(added.error, null);
  assert.equal(added.store.queue[0].method, "POST");
  assert.equal(added.store.queue[0].path, "/api/v1/issues/9/comments");
  assert.equal(added.store.projects[3].issues[9].page.comments[0].pending, true);
  assert.equal(added.store.projects[3].issues[9].page.comments[0].body, "Hello");
  assert.equal(workView(added.store)[0].issues[0].pending, true);
  const uploaded = await uploadQueue(added.store, {
    async read() {
      throw new Error("a comment does not reread the issue");
    },
    async send() {
      return {
        id: 4,
        issue_id: 9,
        author_id: 2,
        body: "Hello",
        created_at: "2026-10-14T17:00:00",
      };
    },
  });
  const comment = uploaded.projects[3].issues[9].page.comments[0];
  assert.equal(comment.id, 4);
  assert.equal(comment.pending, false);
  assert.equal(comment.author, "Cursor");
  assert.equal(uploaded.queue.length, 0);
  assert.equal(uploaded.projects[3].issues[9].pending, false);
});

test("a comment on a new issue follows it onto the server", async () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const filed = queueCreate(store, { projectId: 3, title: "Paint", type: "story", sprint_id: 7 });
  const added = queueComment(filed.store, filed.issueId, "Note", "Cursor");
  const uploaded = await uploadQueue(added.store, {
    async read() {
      throw new Error("a new issue is not read first");
    },
    async send(method, path) {
      if (path.endsWith("/issues")) {
        return {
          id: 20,
          key: "KEEL-20",
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
          created_at: "2026-10-14T17:00:00",
          updated_at: "2026-10-14T17:00:00",
          rollup: null,
        };
      }
      assert.equal(method, "POST");
      assert.equal(path, "/api/v1/issues/20/comments");
      return {
        id: 5,
        issue_id: 20,
        author_id: 2,
        body: "Note",
        created_at: "2026-10-14T17:01:00",
      };
    },
  });
  assert.equal(uploaded.projects[3].issues[20].page.comments[0].body, "Note");
  assert.equal(uploaded.projects[3].issues[20].page.comments[0].pending, false);
  assert.equal(uploaded.queue.length, 0);
});

test("removing a waiting comment drops it, and a saved comment waits to be removed", async () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const added = queueComment(store, 9, "Hello", "Cursor");
  const dropped = queueRemoveComment(added.store, 9, added.commentId);
  assert.equal(dropped.store.queue.length, 0);
  assert.equal(dropped.store.projects[3].issues[9].page.comments.length, 0);
  dropped.store.projects[3].issues[9].page.comments = [
    { id: 4, author: "Cursor", created: "2026-10-14 17:00 UTC", body: "Hello", blocks: [], pending: false },
  ];
  const removed = queueRemoveComment(dropped.store, 9, 4);
  assert.equal(removed.store.queue[0].path, "/api/v1/comments/4");
  assert.equal(removed.store.projects[3].issues[9].page.comments.length, 0);
  const uploaded = await uploadQueue(removed.store, {
    async read() {
      throw new Error("removing a comment does not reread the issue");
    },
    async send() {
      return null;
    },
  });
  assert.equal(uploaded.queue.length, 0);
  assert.equal(uploaded.projects[3].issues[9].page.comments.length, 0);
});

test("the queue lists each change that has not reached the server", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const filed = queueCreate(store, { projectId: 3, title: "New hull", type: "story", status: "todo" });
  store = queueUpdate(filed.store, 9, { title: "Paint the deck" }).store;
  const rows = presentQueue(store);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].action, "Create");
  assert.equal(rows[0].issue, "New hull");
  assert.match(rows[0].detail, /Title: New hull/);
  assert.equal(rows[1].action, "Update");
  assert.equal(rows[1].issue, "KEEL-9 Paint the deck");
  assert.equal(rows[1].project, "KEEL · Keel");
  assert.match(rows[1].detail, /Title: Paint the deck/);
});

test("removing a waiting update restores the issue and sends nothing", async () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = queueUpdate(store, 9, { title: "Boat", status: "done" }, { online: false }).store;
  store = queueUpdate(store, 9, { priority: "p1" }, { online: false }).store;
  assert.deepEqual(store.queue[0].prior, { title: "Paint", status: "todo", priority: "p4" });
  const dropped = dropQueueItem(store, store.queue[0].id);
  assert.equal(dropped.error, null);
  assert.equal(dropped.store.queue.length, 0);
  const issue = dropped.store.projects[3].issues[9];
  assert.equal(issue.raw.title, "Paint");
  assert.equal(issue.raw.status, "todo");
  assert.equal(issue.raw.priority, "p4");
  assert.equal(issue.page.title, "Paint");
  assert.equal(issue.pending, false);
  const uploaded = await uploadQueue(dropped.store, {
    async read() {
      throw new Error("nothing to read");
    },
    async send() {
      throw new Error("nothing to send");
    },
  });
  assert.equal(uploaded.projects[3].issues[9].raw.title, "Paint");
});

test("removing an update keeps a later comment", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = queueUpdate(store, 9, { title: "Boat" }, { online: false }).store;
  const added = queueComment(store, 9, "Hello", "Cursor");
  const dropped = dropQueueItem(added.store, added.store.queue.find((item) => item.kind === "update").id);
  assert.equal(dropped.error, null);
  assert.equal(dropped.store.queue.length, 1);
  assert.equal(dropped.store.queue[0].kind, "comment");
  assert.equal(dropped.store.projects[3].issues[9].raw.title, "Paint");
  assert.equal(dropped.store.projects[3].issues[9].page.comments.length, 1);
  assert.equal(dropped.store.projects[3].issues[9].pending, true);
});

test("removing one waiting comment leaves the other", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const first = queueComment(store, 9, "Hello", "Cursor");
  const second = queueComment(first.store, 9, "Again", "Cursor");
  const dropped = dropQueueItem(second.store, `comment-${first.commentId}`);
  assert.equal(dropped.store.queue.length, 1);
  assert.equal(dropped.store.queue[0].commentId, second.commentId);
  assert.equal(dropped.store.projects[3].issues[9].page.comments.length, 1);
  assert.equal(dropped.store.projects[3].issues[9].page.comments[0].body, "Again");
  assert.equal(dropped.store.projects[3].issues[9].pending, true);
});

test("removing a waiting comment deletion puts the comment back", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store.projects[3].issues[9].page.comments = [
    { id: 4, author: "Cursor", created: "2026-10-14 17:00 UTC", body: "Hello", blocks: [], pending: false },
  ];
  const removed = queueRemoveComment(store, 9, 4);
  const dropped = dropQueueItem(removed.store, removed.store.queue[0].id);
  assert.equal(dropped.error, null);
  assert.equal(dropped.store.queue.length, 0);
  assert.equal(dropped.store.projects[3].issues[9].page.comments.length, 1);
  assert.equal(dropped.store.projects[3].issues[9].page.comments[0].body, "Hello");
  assert.equal(dropped.store.projects[3].issues[9].pending, false);
});

test("removing a waiting delete keeps the issue", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const removed = queueDelete(store, 9);
  const dropped = dropQueueItem(removed.store, "delete-9");
  assert.equal(dropped.error, null);
  assert.equal(dropped.store.queue.length, 0);
  assert.equal(dropped.store.projects[3].issues[9].raw.title, "Paint");
  assert.equal(dropped.store.projects[3].issues[9].pending, false);
});

test("removing a waiting create drops that issue and its comments", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const filed = queueCreate(store, { projectId: 3, title: "New hull", type: "story", parent_id: 9 });
  const added = queueComment(filed.store, filed.issueId, "Note", "Cursor");
  assert.equal(
    added.store.projects[3].issues[9].page.children.some((child) => child.id === filed.issueId),
    true,
  );
  const dropped = dropQueueItem(added.store, `create-${filed.issueId}`);
  assert.equal(dropped.error, null);
  assert.equal(dropped.store.queue.length, 0);
  assert.equal(dropped.store.projects[3].issues[filed.issueId], undefined);
  assert.equal(
    dropped.store.projects[3].issues[9].page.children.some((child) => child.id === filed.issueId),
    false,
  );
});

test("a waiting create with children stays in the queue", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const parent = queueCreate(store, { projectId: 3, title: "Hull", type: "epic" });
  const child = queueCreate(parent.store, {
    projectId: 3,
    title: "Paint",
    type: "subtask",
    parent_id: parent.issueId,
  });
  const dropped = dropQueueItem(child.store, `create-${parent.issueId}`);
  assert.equal(dropped.error, "Move or delete this issue's children first.");
  assert.equal(dropped.store, child.store);
  assert.equal(dropped.store.queue.length, 2);
});

test("removing a changed-conflict update clears the conflict", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = queueUpdate(store, 9, { title: "Boat" }, { online: false }).store;
  store = markConflict(store, 9, { kind: "changed", server: { title: "Server" } });
  const dropped = dropQueueItem(store, store.queue[0].id);
  assert.equal(dropped.store.projects[3].issues[9].raw.title, "Paint");
  assert.equal(dropped.store.projects[3].issues[9].conflict, null);
  assert.equal(dropped.store.projects[3].issues[9].pending, false);
});

test("removing an update keeps a deleted-on-server conflict", () => {
  let store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  store = queueUpdate(store, 9, { title: "Boat" }, { online: false }).store;
  store = markConflict(store, 9, { kind: "deleted" });
  const dropped = dropQueueItem(store, store.queue[0].id);
  assert.equal(dropped.store.queue.length, 0);
  assert.equal(dropped.store.projects[3].issues[9].raw.title, "Paint");
  assert.equal(dropped.store.projects[3].issues[9].conflict.kind, "deleted");
  assert.equal(dropped.store.projects[3].issues[9].pending, true);
});

test("removing a queue item that is already gone reports that", () => {
  const store = applyRefresh(emptyStore(), [snapshot()], { people: [], labels: [] });
  const dropped = dropQueueItem(store, "missing");
  assert.equal(dropped.error, "That change is no longer waiting.");
  assert.equal(dropped.store, store);
});
