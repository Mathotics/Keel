const assert = require("node:assert/strict");
const test = require("node:test");

const { NOTHING, SAVED_BOARD, boardView } = require("./board");

function issue(overrides) {
  return {
    id: 9,
    key: "KEEL-9",
    number: 9,
    project_id: 3,
    type: "story",
    title: "Paint",
    status: "todo",
    priority: "p4",
    assignee_id: null,
    sprint_id: 7,
    unresolved_blockers: 0,
    ...overrides,
  };
}

function library(issues) {
  const stored = {};
  for (const item of issues || []) {
    stored[item.id] = { id: item.id, raw: item, pending: Boolean(item.pending) };
  }
  return {
    people: [{ id: 4, display_name: "Cursor" }],
    projects: {
      3: {
        id: 3,
        key: "KEEL",
        enabled: true,
        sprint: { id: 7, name: "This month", state: "active" },
        issues: stored,
      },
      8: {
        id: 8,
        key: "DOCS",
        enabled: true,
        sprint: { id: 4, name: "Docs sprint", state: "active" },
        issues: {
          3: {
            id: 3,
            raw: issue({
              id: 3,
              key: "DOCS-3",
              number: 3,
              project_id: 8,
              title: "Guide",
              status: "in_review",
              sprint_id: 4,
            }),
          },
        },
      },
    },
  };
}

function boardFor(projectId, issues, lanes) {
  const columns = ["todo", "in_progress", "in_review", "blocked", "done", "cancelled"].map((status) => ({
    status,
    label: status,
    issues: issues.filter((item) => item.status === status && item.project_id === projectId),
  }));
  return {
    project_id: projectId,
    columns,
    lanes: lanes || [{ sprint_id: projectId === 3 ? 7 : 4, name: projectId === 3 ? "This month" : "Docs sprint", state: "active" }],
  };
}

test("keeps the six workflow columns and hides an empty board message when cards exist", () => {
  const view = boardView({
    library: library([issue({ assignee_id: 4, unresolved_blockers: 2 })]),
    boards: [boardFor(3, [issue({ assignee_id: 4, unresolved_blockers: 2 })])],
    projectId: 3,
  });
  assert.deepEqual(
    view.columns.map((column) => column.label),
    ["To Do", "In Progress", "In Review", "Blocked", "Done", "Cancelled"],
  );
  assert.equal(view.title, "KEEL board");
  assert.equal(view.empty, "");
  assert.equal(view.columns[0].cards[0].assignee, "Cursor");
  assert.equal(view.columns[0].cards[0].priority, "P4");
  assert.equal(view.columns[0].cards[0].typeLabel, "Story");
  assert.equal(view.columns[0].cards[0].blockers, 2);
  assert.equal(view.columns[0].cards[0].sprintName, "This month");
});

test("merges projects on the master board and can show one project", () => {
  const boards = [
    boardFor(3, [issue()]),
    boardFor(8, [issue({ id: 3, key: "DOCS-3", number: 3, project_id: 8, title: "Guide", status: "in_review", sprint_id: 4 })]),
  ];
  const master = boardView({ library: library([issue()]), boards, projectId: null });
  const keys = master.columns.flatMap((column) => column.cards.map((card) => card.key));
  assert.deepEqual(keys, ["KEEL-9", "DOCS-3"]);
  assert.equal(master.columns[0].cards[0].sprintName, "KEEL / This month");
  const one = boardView({ library: library([issue()]), boards, projectId: 8 });
  assert.deepEqual(
    one.columns.flatMap((column) => column.cards.map((card) => card.key)),
    ["DOCS-3"],
  );
  assert.equal(one.title, "DOCS board");
});

test("a waiting status on the phone wins over the server column", () => {
  const local = issue({ status: "in_progress", pending: true });
  const remote = issue({ status: "todo" });
  const view = boardView({
    library: library([local]),
    boards: [boardFor(3, [remote])],
    projectId: 3,
  });
  assert.equal(view.columns[0].cards.length, 0);
  assert.equal(view.columns[1].cards[0].key, "KEEL-9");
  assert.equal(view.columns[1].cards[0].pending, true);
});

test("open work returned for a completed sprint stays, and omitted closed work stays off", () => {
  const open = issue({ id: 11, key: "KEEL-11", number: 11, status: "blocked", sprint_id: 2 });
  const closed = issue({ id: 12, key: "KEEL-12", number: 12, status: "done", sprint_id: 2 });
  const view = boardView({
    library: library([closed]),
    boards: [
      boardFor(3, [open], [{ sprint_id: 2, name: "Last month", state: "completed" }]),
    ],
    projectId: 3,
  });
  const keys = view.columns.flatMap((column) => column.cards.map((card) => card.key));
  assert.deepEqual(keys, ["KEEL-11"]);
  assert.equal(view.columns[3].cards[0].sprintName, "Last month");
});

test("offline shows the saved active sprint and says other issues need a connection", () => {
  const saved = library([
    issue({ status: "done" }),
    issue({ id: 15, key: "KEEL-15", number: 15, status: "todo", sprint_id: 2 }),
  ]);
  const view = boardView({ library: saved, boards: null, projectId: null });
  const keys = view.columns.flatMap((column) => column.cards.map((card) => card.key));
  assert.deepEqual(keys, ["DOCS-3", "KEEL-9"]);
  assert.equal(view.banner, SAVED_BOARD);
  assert.equal(view.columns[4].cards[0].key, "KEEL-9");
  const empty = boardView({
    library: { people: [], projects: {} },
    boards: [],
    projectId: null,
  });
  assert.equal(empty.empty, NOTHING);
  assert.equal(empty.columns.length, 6);
});
