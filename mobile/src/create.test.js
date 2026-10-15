const assert = require("node:assert/strict");
const test = require("node:test");

const { prepareCreate, prepareUpdate } = require("./create");
const { applyRefresh, queueCreate, workView } = require("./offline");
const { uploadQueue } = require("./sync");

function store() {
  return applyRefresh(
    { projects: {}, people: [{ id: 2, display_name: "Jacob Hootman" }], labels: [], queue: [] },
    [
      {
        project: { id: 3, key: "KEEL", name: "Keel" },
        sprint: { id: 7, name: "This month", state: "active" },
        issues: [],
      },
    ],
    { people: [{ id: 2, display_name: "Jacob Hootman" }], labels: [] },
  );
}

test("a title is required and an epic cannot have a parent", () => {
  assert.equal(prepareCreate({ title: "  ", projectId: 3 }).error, "Enter a title.");
  assert.match(
    prepareCreate({
      title: "Too big",
      projectId: 3,
      type: "epic",
      parent: { id: 1, type: "epic", projectId: 3 },
    }).error,
    /epic/i,
  );
});

test("a story can sit under an epic and effort is read", () => {
  const prepared = prepareCreate({
    title: "Paint",
    projectId: 3,
    type: "story",
    parent: { id: 4, type: "epic", projectId: 3 },
    estimate: "1h 30m",
    start: "2026-10-12 09:00",
    labels: "hull, deck",
  });
  assert.equal(prepared.error, null);
  assert.equal(prepared.draft.parent_id, 4);
  assert.equal(prepared.draft.estimate_minutes, 90);
  assert.deepEqual(prepared.draft.labels, ["hull", "deck"]);
  assert.equal(prepared.draft.start_at, "2026-10-12T09:00:00");
});

test("a new issue waits on the phone without a key", async () => {
  const prepared = prepareCreate({
    title: "Paint",
    projectId: 3,
    sprintId: 7,
    type: "story",
  });
  const filed = queueCreate(store(), prepared.draft);
  assert.equal(filed.error, null);
  const row = workView(filed.store)[0].issues[0];
  assert.equal(row.key, "");
  assert.equal(row.pending, true);
  assert.equal(filed.store.queue[0].kind, "create");
  assert.equal(filed.store.queue[0].method, "POST");

  const uploaded = await uploadQueue(filed.store, {
    async read() {
      throw new Error("a new issue is not on the server");
    },
    async send() {
      return {
        id: 20,
        key: "KEEL-20",
        project_id: 3,
        title: "Paint",
        type: "story",
        status: "todo",
        priority: "p4",
        assignee_id: null,
        reporter_id: 2,
        labels: [],
        parent_id: null,
        sprint_id: 7,
        description: "",
        estimate_minutes: null,
        remaining_minutes: null,
        start_at: null,
        due_at: null,
        created_at: "2026-10-12T00:00:00",
        updated_at: "2026-10-12T00:00:00",
        rollup: null,
      };
    },
  });
  const saved = workView(uploaded)[0].issues[0];
  assert.equal(saved.key, "KEEL-20");
  assert.equal(saved.pending, false);
  assert.equal(uploaded.queue.length, 0);
});

const savedIssue = {
  id: 9,
  title: "Paint",
  type: "story",
  description: "",
  status: "todo",
  priority: "p4",
  assignee_id: null,
  parent_id: null,
  sprint_id: 7,
  estimate_minutes: 90,
  remaining_minutes: null,
  start_at: "2026-10-12T09:00:00",
  due_at: null,
  labels: ["hull"],
};

function updateInput(overrides) {
  return {
    issue: savedIssue,
    title: "Paint",
    projectId: 3,
    type: "story",
    description: "",
    status: "todo",
    priority: "p4",
    assigneeId: null,
    parent: null,
    sprintId: 7,
    activeSprintId: 7,
    online: false,
    estimate: "1h 30m",
    remaining: "",
    start: "2026-10-12 09:00",
    due: "",
    labels: "hull",
    childTypes: [],
    ...overrides,
  };
}

test("an unchanged issue sends no fields", () => {
  const prepared = prepareUpdate(updateInput());
  assert.equal(prepared.error, null);
  assert.deepEqual(prepared.changes, {});
});

test("a title change is the only field sent", () => {
  const prepared = prepareUpdate(updateInput({ title: "Boat" }));
  assert.equal(prepared.error, null);
  assert.deepEqual(prepared.changes, { title: "Boat" });
});

test("existing children block a type the server would refuse", () => {
  const prepared = prepareUpdate(updateInput({ type: "subtask", childTypes: ["story"] }));
  assert.match(prepared.error, /Existing story children/);
});

test("the backlog needs a connection and the active sprint does not", () => {
  const offline = prepareUpdate(updateInput({ sprintId: null }));
  assert.match(offline.error, /connection/);
  const online = prepareUpdate(updateInput({ sprintId: null, online: true }));
  assert.equal(online.error, null);
  assert.deepEqual(online.changes, { sprint_id: null });
});
