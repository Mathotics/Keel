const assert = require("node:assert/strict");
const test = require("node:test");

const { inboxView, localCalendarDay } = require("./inbox");

const TODAY = "2026-10-14";

function issue(overrides) {
  return {
    id: 9,
    key: "KEEL-9",
    number: 9,
    project_id: 3,
    title: "Paint",
    status: "todo",
    assignee_id: 4,
    due_at: null,
    start_at: null,
    sprint_id: 7,
    series_id: null,
    occurrence_on: null,
    unresolved_blockers: 0,
    completedOn: null,
    ...overrides,
  };
}

function library() {
  return {
    projects: {
      3: {
        id: 3,
        key: "KEEL",
        enabled: true,
        sprint: { id: 7, name: "This month" },
        issues: {},
      },
    },
  };
}

test("a completion timestamp uses the phone's local day", () => {
  assert.equal(localCalendarDay("2026-10-14T03:00:00", 240), "2026-10-13");
  assert.equal(localCalendarDay("2026-10-14T15:00:00", 240), "2026-10-14");
});

test("empty sections stay hidden and the same issue can sit in more than one", () => {
  const view = inboxView({
    library: library(),
    userId: 4,
    today: TODAY,
    remote: [
      issue({ due_at: "2026-10-14T09:00:00", unresolved_blockers: 2 }),
      issue({ id: 10, key: "KEEL-10", number: 10, due_at: "2026-10-18T09:00:00" }),
      issue({ id: 11, key: "KEEL-11", number: 11, due_at: "2026-10-28T09:00:00" }),
      issue({ id: 12, key: "KEEL-12", number: 12, due_at: "2026-11-02T09:00:00", start_at: "2026-10-20T09:00:00" }),
    ],
    offsetMinutes: 0,
  });
  const titles = view.sections.map((section) => section.title);
  assert.deepEqual(titles, [
    "Now",
    "Due or overdue",
    "Due this week",
    "Due this month",
    "Assigned to me",
    "Blocked",
    "In the active sprint",
  ]);
  assert.equal(view.sections[0].rows[0].blockers, 2);
  assert.equal(view.sections.every((section) => section.needsConnection), false);
  assert.equal(view.empty, "");
});

test("now lists started, due, and in progress once each", () => {
  const view = inboxView({
    library: library(),
    userId: 4,
    today: TODAY,
    remote: [
      issue({ id: 1, key: "KEEL-1", number: 1, due_at: "2026-10-10T09:00:00" }),
      issue({ id: 2, key: "KEEL-2", number: 2, due_at: "2026-10-14T18:00:00", status: "in_progress" }),
      issue({ id: 3, key: "KEEL-3", number: 3, start_at: "2026-10-12T09:00:00", due_at: "2026-10-20T09:00:00" }),
      issue({ id: 4, key: "KEEL-4", number: 4, status: "in_progress" }),
      issue({ id: 5, key: "KEEL-5", number: 5, due_at: "2026-10-20T09:00:00" }),
      issue({ id: 6, key: "KEEL-6", number: 6, status: "done", due_at: "2026-10-01T09:00:00", completedOn: "2026-10-14T15:00:00" }),
    ],
  });
  const now = view.sections.find((section) => section.key === "now");
  assert.deepEqual(now.rows.map((row) => row.key), ["KEEL-1", "KEEL-2", "KEEL-3", "KEEL-4"]);
  assert.equal(now.rows.filter((row) => row.key === "KEEL-2").length, 1);
});

test("done work stays in the active sprint and completed today, not in assigned", () => {
  const view = inboxView({
    library: library(),
    userId: 4,
    today: TODAY,
    remote: [
      issue({ status: "done", completedOn: "2026-10-14T15:00:00" }),
      issue({ id: 8, key: "KEEL-8", number: 8, status: "cancelled" }),
    ],
    offsetMinutes: 240,
  });
  const names = Object.fromEntries(view.sections.map((section) => [section.key, section.rows.map((row) => row.key)]));
  assert.deepEqual(names.sprint, ["KEEL-9", "KEEL-8"]);
  assert.deepEqual(names.completed, ["KEEL-9"]);
  assert.equal(names.assigned, undefined);
});

test("offline shows saved sprint issues and marks sections that need more", () => {
  const saved = library();
  saved.projects[3].issues[9] = {
    id: 9,
    pending: false,
    raw: issue({ due_at: "2026-10-14T09:00:00", series_id: 2, occurrence_on: "2026-10-14" }),
  };
  const view = inboxView({ library: saved, userId: 4, today: TODAY, remote: null });
  const due = view.sections.find((section) => section.key === "due");
  const sprint = view.sections.find((section) => section.key === "sprint");
  const waiting = view.sections.find((section) => section.key === "waiting");
  assert.equal(view.banner.length > 0, true);
  assert.equal(due.needsConnection, true);
  assert.equal(due.rows[0].key, "KEEL-9");
  assert.equal(sprint.needsConnection, false);
  assert.equal(waiting.rows[0].key, "KEEL-9");
  assert.equal(view.sections.some((section) => section.key === "completed"), false);
  assert.equal(view.sections.some((section) => section.key === "week"), false);
});

test("a waiting local issue keeps the phone's status", () => {
  const saved = library();
  saved.projects[3].issues[9] = {
    id: 9,
    pending: true,
    raw: issue({ status: "in_progress" }),
  };
  const view = inboxView({
    library: saved,
    userId: 4,
    today: TODAY,
    remote: [issue({ status: "todo" })],
  });
  const assigned = view.sections.find((section) => section.key === "assigned");
  assert.equal(assigned.rows[0].status, "in_progress");
  assert.equal(assigned.rows[0].pending, true);
});
