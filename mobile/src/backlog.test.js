const assert = require("node:assert/strict");
const test = require("node:test");

const { NEEDS_CONNECTION, NOTHING, NO_SPRINT, backlogView } = require("./backlog");

function issue(overrides) {
  return {
    id: 9,
    key: "KEEL-9",
    project_id: 3,
    type: "story",
    title: "Paint",
    status: "todo",
    priority: "p4",
    assignee_id: null,
    sprint_id: null,
    unresolved_blockers: 0,
    start_at: null,
    due_at: null,
    created_at: "2026-10-02T00:00:00",
    ...overrides,
  };
}

function library(stored) {
  return {
    people: [{ id: 4, display_name: "Cursor" }],
    projects: {
      3: {
        id: 3,
        key: "KEEL",
        enabled: true,
        sprint: { id: 7, name: "This month", state: "active" },
        issues: stored || {},
      },
    },
  };
}

const sprints = [
  { id: 2, project_id: 3, name: "Last month", state: "completed" },
  { id: 7, project_id: 3, name: "This month", state: "active" },
  { id: 8, project_id: 3, name: "Next month", state: "planned" },
];

test("lists unscheduled unfinished issues oldest first with active and planned sprints", () => {
  const view = backlogView({
    library: library(),
    projectId: 3,
    issues: [
      issue({ id: 4, key: "KEEL-4", title: "Older", created_at: "2026-10-01T00:00:00", assignee_id: 4, unresolved_blockers: 1, due_at: "2026-10-20T15:00:00" }),
      issue({ status: "done", id: 5, key: "KEEL-5" }),
      issue({ sprint_id: 7, id: 6, key: "KEEL-6" }),
      issue(),
    ],
    sprints,
  });
  assert.equal(view.title, "KEEL backlog");
  assert.deepEqual(view.rows.map((row) => row.key), ["KEEL-4", "KEEL-9"]);
  assert.equal(view.rows[0].assignee, "Cursor");
  assert.equal(view.rows[0].blockers, 1);
  assert.equal(view.rows[0].due, "2026-10-20 15:00 UTC");
  assert.deepEqual(view.sprints.map((sprint) => sprint.label), [
    "This month (Active)",
    "Next month (Planned)",
  ]);
  assert.equal(view.empty, "");
});

test("a waiting local schedule leaves the backlog and a new unscheduled issue joins it", () => {
  const view = backlogView({
    library: library({
      9: { id: 9, pending: true, raw: issue({ sprint_id: 7, status: "in_progress" }) },
      [-1]: { id: -1, pending: true, raw: issue({ id: -1, key: "", title: "Fresh", created_at: "2026-10-03T00:00:00" }) },
    }),
    projectId: 3,
    issues: [issue()],
    sprints,
  });
  assert.deepEqual(view.rows.map((row) => row.title), ["Fresh"]);
  assert.equal(view.rows[0].pending, true);
  assert.equal(view.rows[0].key, "");
});

test("offline asks for a connection and an empty backlog says so", () => {
  const offline = backlogView({ library: library(), projectId: 3, issues: null, sprints: null });
  assert.equal(offline.banner, NEEDS_CONNECTION);
  assert.equal(offline.rows.length, 0);
  assert.equal(offline.sprints.length, 0);
  const empty = backlogView({ library: library(), projectId: 3, issues: [], sprints: [] });
  assert.equal(empty.empty, NOTHING);
  assert.equal(empty.noSprint, "");
  const unschedulable = backlogView({
    library: library(),
    projectId: 3,
    issues: [issue()],
    sprints: [{ id: 2, project_id: 3, name: "Last month", state: "completed" }],
  });
  assert.equal(unschedulable.noSprint, NO_SPRINT);
});
