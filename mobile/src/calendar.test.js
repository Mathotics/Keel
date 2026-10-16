const test = require("node:test");
const assert = require("node:assert/strict");

const { calendarView, focusForView, moveFocus } = require("./calendar");

const TODAY = "2026-10-14";

function issue(raw) {
  return {
    pending: false,
    raw,
  };
}

function library() {
  return {
    projects: {
      3: {
        id: 3,
        key: "KEEL",
        enabled: true,
        sprint: { id: 7, name: "Now", state: "active" },
        issues: {
          9: issue({
            id: 9,
            key: "KEEL-9",
            number: 9,
            title: "Paint the door",
            type: "story",
            status: "todo",
            assignee_id: 4,
            sprint_id: 7,
            start_at: "2026-10-14T13:00:00Z",
            due_at: "2026-10-16T17:00:00Z",
            created_at: "2026-10-01T15:00:00Z",
          }),
          10: issue({
            id: 10,
            key: "KEEL-10",
            number: 10,
            title: "Unscheduled",
            type: "story",
            status: "todo",
            assignee_id: 4,
            sprint_id: null,
            start_at: "2026-10-14T13:00:00Z",
            due_at: "2026-10-14T17:00:00Z",
            created_at: "2026-10-02T15:00:00Z",
          }),
          11: issue({
            id: 11,
            key: "KEEL-11",
            number: 11,
            title: "Someone else",
            type: "epic",
            status: "done",
            assignee_id: 8,
            sprint_id: 7,
            start_at: "2026-10-14T13:00:00Z",
            due_at: "2026-10-14T15:00:00Z",
            created_at: "2026-10-03T15:00:00Z",
          }),
        },
      },
    },
  };
}

test("an empty month still shows its weeks", () => {
  const view = calendarView({
    library: { projects: {} },
    remote: [],
    mode: "start",
    view: "month",
    focus: TODAY,
    today: TODAY,
    userId: 4,
  });
  assert.equal(view.label, "October 2026");
  assert.equal(view.empty, "Nothing dated falls in this month.");
  assert.equal(view.banner, "");
  assert.equal(view.weeks[0].days[0].date, "2026-09-28");
  assert.equal(view.weeks[0].days[0].inMonth, false);
  assert.equal(view.weeks[2].days[2].date, TODAY);
  assert.equal(view.weeks[2].days[2].isToday, true);
});

test("start to due spans the saved sprint and a project calendar keeps other people", () => {
  const mine = calendarView({
    library: library(),
    remote: null,
    mode: "start",
    view: "month",
    focus: TODAY,
    today: TODAY,
    userId: 4,
  });
  assert.match(mine.banner, /saved active sprint/);
  const fourteenth = mine.weeks[2].days[2];
  assert.deepEqual(fourteenth.issues.map((row) => row.key), ["KEEL-9"]);
  assert.equal(fourteenth.issues[0].statusLabel, "To Do");
  assert.equal(mine.weeks[2].days[4].issues[0].key, "KEEL-9");
  assert.equal(mine.weeks[2].days[5].issues.length, 0);

  const project = calendarView({
    library: library(),
    remote: null,
    mode: "start",
    view: "day",
    focus: TODAY,
    today: TODAY,
    projectId: 3,
    userId: 4,
  });
  assert.deepEqual(project.days[0].issues.map((row) => row.key), ["KEEL-9", "KEEL-11"]);
  assert.equal(project.days[0].issues[0].time, "From 1 PM");
  assert.equal(project.label, "Wednesday, October 14, 2026");
});

test("online dates outside the sprint appear, and a waiting change wins", () => {
  const store = library();
  store.projects[3].issues[9].pending = true;
  store.projects[3].issues[9].raw.due_at = "2026-10-14T18:00:00Z";
  const view = calendarView({
    library: store,
    remote: [
      {
        id: 10,
        key: "KEEL-10",
        number: 10,
        project_id: 3,
        projectKey: "KEEL",
        title: "Unscheduled",
        type: "story",
        status: "todo",
        assignee_id: 4,
        start_at: "2026-10-20T09:00:00Z",
        due_at: "2026-10-20T10:00:00Z",
      },
      {
        id: 9,
        key: "KEEL-9",
        number: 9,
        project_id: 3,
        title: "Paint the door",
        type: "story",
        status: "todo",
        assignee_id: 4,
        start_at: "2026-10-14T13:00:00Z",
        due_at: "2026-10-16T17:00:00Z",
      },
    ],
    mode: "start",
    view: "week",
    focus: "2026-10-20",
    today: TODAY,
    userId: 4,
  });
  assert.equal(view.banner, "");
  const tuesday = view.days.find((day) => day.date === "2026-10-20");
  assert.deepEqual(tuesday.issues.map((row) => row.key), ["KEEL-10"]);
  const wednesday = calendarView({
    library: store,
    remote: view && [],
    mode: "start",
    view: "day",
    focus: TODAY,
    today: TODAY,
    userId: 4,
  });
  assert.equal(wednesday.days[0].issues[0].time, "1 PM – 6 PM");
});

test("completed and created use the local day, and cancelled stays off completed", () => {
  const store = library();
  store.projects[3].issues[12] = issue({
    id: 12,
    key: "KEEL-12",
    number: 12,
    title: "Finished late",
    type: "subtask",
    status: "done",
    assignee_id: 4,
    sprint_id: 7,
    start_at: null,
    due_at: null,
    created_at: "2026-10-01T12:00:00Z",
  });
  store.projects[3].issues[11].raw.status = "cancelled";
  const completed = calendarView({
    library: store,
    remote: [
      {
        id: 12,
        key: "KEEL-12",
        number: 12,
        project_id: 3,
        title: "Finished late",
        type: "subtask",
        status: "done",
        assignee_id: 4,
        start_at: null,
        due_at: null,
        created_at: "2026-10-01T12:00:00Z",
      },
    ],
    completedAt: { 12: "2026-10-15T02:00:00Z" },
    mode: "completed",
    view: "day",
    focus: TODAY,
    today: TODAY,
    userId: 4,
    offsetMinutes: 240,
  });
  assert.equal(completed.empty, "");
  assert.equal(completed.days[0].issues[0].key, "KEEL-12");
  assert.equal(completed.days[0].issues[0].time, "10 PM");
  assert.equal(completed.days[0].issues[0].color, "#B45309");

  const created = calendarView({
    library: store,
    remote: null,
    mode: "created",
    view: "month",
    focus: TODAY,
    today: TODAY,
    userId: 4,
    offsetMinutes: 0,
  });
  const first = created.weeks[0].days[3];
  assert.equal(first.date, "2026-10-01");
  assert.deepEqual(first.issues.map((row) => row.key), ["KEEL-9", "KEEL-12"]);
});

test("previous, next, and today stay on the open view", () => {
  assert.equal(moveFocus("month", TODAY, TODAY, -1), "2026-09-01");
  assert.equal(moveFocus("month", TODAY, TODAY, 1), "2026-11-01");
  assert.equal(moveFocus("week", TODAY, TODAY, 1), "2026-10-19");
  assert.equal(moveFocus("day", TODAY, TODAY, -1), "2026-10-13");
  assert.equal(moveFocus("day", "2026-01-02", TODAY, "today"), TODAY);
  assert.equal(focusForView("week", "month", "2026-11-03", TODAY), "2026-11-01");
  assert.equal(focusForView("day", "month", TODAY, TODAY), TODAY);
  assert.equal(focusForView("month", "day", TODAY, TODAY), TODAY);
});

test("a status filter narrows dated issues and leaves the month in place", () => {
  const view = calendarView({
    library: library(),
    remote: null,
    mode: "start",
    view: "month",
    focus: TODAY,
    today: TODAY,
    projectId: 3,
    userId: 4,
    filter: {
      types: ["epic", "story", "subtask"],
      statuses: ["done"],
      priorities: [],
      sprints: [],
      projects: [],
      assignees: [],
      reporters: [],
      labels: [],
    },
  });
  const keys = view.weeks.flatMap((week) => week.days.flatMap((day) => day.issues.map((row) => row.key)));
  assert.deepEqual([...new Set(keys)], ["KEEL-11"]);
  assert.equal(view.label, "October 2026");
});
