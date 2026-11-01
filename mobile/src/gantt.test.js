const test = require("node:test");
const assert = require("node:assert/strict");

const { ganttView, focusForView, moveFocus } = require("./gantt");

const TODAY = "2026-10-15";

function issue(raw) {
  return { pending: false, raw };
}

function library() {
  return {
    projects: {
      3: {
        id: 3,
        key: "KEEL",
        enabled: true,
        issues: {
          1: issue({
            id: 1,
            key: "KEEL-1",
            number: 1,
            title: "First",
            type: "story",
            status: "todo",
            assignee_id: 4,
            parent_id: null,
            start_at: "2026-10-03T13:00:00Z",
            due_at: "2026-10-06T17:00:00Z",
          }),
          2: issue({
            id: 2,
            key: "KEEL-2",
            number: 2,
            title: "Second",
            type: "story",
            status: "done",
            assignee_id: 4,
            parent_id: 1,
            start_at: "2026-10-02T13:00:00Z",
            due_at: "2026-10-04T17:00:00Z",
          }),
          3: issue({
            id: 3,
            key: "KEEL-3",
            number: 3,
            title: "Related",
            type: "epic",
            status: "todo",
            assignee_id: 8,
            parent_id: null,
            start_at: "2026-10-20T13:00:00Z",
            due_at: "2026-10-21T17:00:00Z",
          }),
          4: issue({
            id: 4,
            key: "KEEL-4",
            number: 4,
            title: "Undated",
            type: "story",
            status: "todo",
            assignee_id: 4,
            parent_id: null,
          }),
        },
      },
    },
  };
}

function open(extra) {
  return ganttView({
    library: library(),
    remote: null,
    view: "month",
    focus: TODAY,
    today: TODAY,
    userId: 4,
    ...extra,
  });
}

test("an empty month still shows one column per day", () => {
  const view = ganttView({
    library: { projects: {} },
    remote: [],
    view: "month",
    focus: TODAY,
    today: TODAY,
    userId: 4,
  });
  assert.equal(view.label, "October 2026");
  assert.equal(view.empty, "Nothing dated falls in this month.");
  assert.equal(view.banner, "");
  assert.equal(view.columns.length, 31);
  assert.equal(view.columns[0].mark, "1");
  assert.equal(view.columns[0].dow, "T");
  assert.equal(view.todayColumn, 15);
  assert.equal(view.columns[14].isToday, true);
});

test("mine keeps done work, indents a child, and leaves other people off", () => {
  const view = open();
  assert.match(view.banner, /saved copy/);
  assert.deepEqual(view.rows.map((row) => row.key), ["KEEL-1", "KEEL-2"]);
  assert.deepEqual(view.rows.map((row) => row.depth), [0, 1]);
  assert.equal(view.rows[0].column, 3);
  assert.equal(view.rows[0].length, 4);
  assert.equal(view.rows[0].point, false);
  assert.equal(view.rows[1].statusLabel, "Done");
  assert.equal(view.rows[1].column, 2);
  assert.equal(view.rows[1].length, 3);
});

test("a project chart keeps other people's dated issues", () => {
  const view = open({ projectId: 3 });
  assert.deepEqual(view.rows.map((row) => row.key), ["KEEL-1", "KEEL-2", "KEEL-3"]);
});

test("the status filter removes a done row and drops its link", () => {
  const view = open({
    projectId: 3,
    filter: { types: ["epic", "story", "subtask"], statuses: ["todo"] },
    links: [
      { source_id: 1, target_id: 2, kind: "blocks" },
      { source_id: 1, target_id: 3, kind: "relates_to" },
    ],
  });
  assert.deepEqual(view.rows.map((row) => row.key), ["KEEL-1", "KEEL-3"]);
  assert.equal(view.links.length, 1);
  assert.equal(view.links[0].kind, "relates_to");
  assert.equal(view.links[0].text, "KEEL-1 relates to KEEL-3");
  assert.equal(view.links[0].path, "M 4 0.5 L 4 0.92 L 20 0.92 L 20 1.5");
  assert.equal(view.links[0].tip, "");
});

test("a blocks arrow runs from the finish toward the start", () => {
  const view = open({
    links: [{ source_id: 1, target_id: 2, kind: "blocks" }],
  });
  assert.equal(view.links.length, 1);
  assert.equal(view.links[0].path, "M 6 0.5 L 6.45 0.5 L 6.45 1.32 L 0.55 1.32 L 0.55 1.5 L 1 1.5");
  assert.equal(view.links[0].tip, "right");
  assert.equal(view.legend, "A solid arrow means blocks. A dashed line means relates to.");
});

test("a forward blocks arrow stays between the two bars", () => {
  const view = ganttView({
    library: {
      projects: {
        3: {
          id: 3,
          key: "KEEL",
          enabled: true,
          issues: {
            1: issue({
              id: 1,
              key: "KEEL-1",
              number: 1,
              title: "First",
              type: "story",
              status: "todo",
              assignee_id: 4,
              start_at: "2026-10-03",
              due_at: "2026-10-06",
            }),
            2: issue({
              id: 2,
              key: "KEEL-2",
              number: 2,
              title: "Second",
              type: "story",
              status: "todo",
              assignee_id: 4,
              start_at: "2026-10-10",
              due_at: "2026-10-12",
            }),
          },
        },
      },
    },
    remote: null,
    links: [{ source_id: 1, target_id: 2, kind: "blocks" }],
    view: "month",
    focus: TODAY,
    today: TODAY,
    userId: 4,
  });
  assert.equal(view.links[0].path, "M 6 0.5 L 6.45 0.5 L 6.45 1.5 L 9 1.5");
  assert.equal(view.links[0].tip, "right");
});

test("a quarter is one column per week and a year is one column per month", () => {
  const quarter = open({ view: "quarter", projectId: 3 });
  assert.equal(quarter.label, "October\u2013December 2026");
  assert.equal(quarter.columns.length, 14);
  assert.equal(quarter.columns[0].mark, "Sep 28");
  assert.equal(quarter.todayColumn, 3);
  const first = quarter.rows.find((row) => row.key === "KEEL-1");
  assert.equal(first.column, 1);
  assert.equal(first.length, 2);
  assert.equal(first.point, false);

  const year = open({ view: "year", projectId: 3 });
  assert.equal(year.label, "2026");
  assert.equal(year.columns.length, 12);
  assert.equal(year.columns[0].mark, "Jan");
  assert.equal(year.todayColumn, 10);
  assert.equal(year.rows[0].column, 10);
  assert.equal(year.rows[0].length, 1);
  assert.equal(year.rows[0].point, false);

  const empty = ganttView({
    library: library(),
    remote: [],
    view: "year",
    focus: "2025-06-01",
    today: TODAY,
    userId: 4,
  });
  assert.equal(empty.label, "2025");
  assert.equal(empty.empty, "Nothing dated falls in this year.");
  assert.equal(empty.todayColumn, null);
});

test("a bar that runs past the page is clipped", () => {
  const view = ganttView({
    library: {
      projects: {
        3: {
          id: 3,
          key: "KEEL",
          enabled: true,
          issues: {
            8: issue({
              id: 8,
              key: "KEEL-8",
              number: 8,
              title: "Across",
              type: "story",
              status: "todo",
              assignee_id: 4,
              start_at: "2026-09-28",
              due_at: "2026-10-02",
            }),
            9: issue({
              id: 9,
              key: "KEEL-9",
              number: 9,
              title: "One day",
              type: "subtask",
              status: "cancelled",
              assignee_id: 4,
              start_at: "2026-10-15",
              due_at: "2026-10-15",
            }),
          },
        },
      },
    },
    remote: null,
    view: "month",
    focus: TODAY,
    today: TODAY,
    userId: 4,
  });
  assert.equal(view.rows[0].continuesBefore, true);
  assert.equal(view.rows[0].column, 1);
  assert.equal(view.rows[0].length, 2);
  assert.equal(view.rows[1].point, true);
  assert.equal(view.rows[1].column, 15);
  assert.equal(view.rows[1].color, "#B45309");
});

test("previous, next, and today stay on the scale", () => {
  assert.equal(moveFocus("month", "2026-10-15", TODAY, 1), "2026-11-01");
  assert.equal(moveFocus("month", "2026-10-15", TODAY, -1), "2026-09-01");
  assert.equal(moveFocus("quarter", "2026-11-02", TODAY, 1), "2027-01-01");
  assert.equal(moveFocus("quarter", "2026-11-02", TODAY, "today"), "2026-10-01");
  assert.equal(moveFocus("year", "2026-10-15", TODAY, 1), "2027-01-01");
  assert.equal(moveFocus("year", "2024-03-01", TODAY, "today"), "2026-01-01");
});

test("changing scale lands on today when today is in view", () => {
  assert.equal(focusForView("quarter", "month", "2026-10-15", TODAY), "2026-10-01");
  assert.equal(focusForView("year", "month", "2026-10-15", TODAY), "2026-01-01");
  assert.equal(focusForView("month", "year", "2026-01-01", TODAY), "2026-10-01");
  assert.equal(focusForView("quarter", "year", "2026-01-01", TODAY), "2026-10-01");
  assert.equal(focusForView("month", "year", "2024-01-01", TODAY), "2024-01-01");
  assert.equal(focusForView("quarter", "year", "2024-01-01", TODAY), "2024-01-01");
  assert.equal(focusForView("month", "quarter", "2026-10-01", TODAY), "2026-10-01");
  assert.equal(focusForView("month", "quarter", "2026-01-01", TODAY), "2026-01-01");
});
