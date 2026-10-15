const assert = require("node:assert/strict");
const test = require("node:test");

const {
  completionNotice,
  planningView,
  prepareSprint,
  prepareSprintUpdate,
  sprintDetail,
} = require("./planning");

function library() {
  return {
    people: [{ id: 4, display_name: "Cursor" }],
    projects: {
      3: {
        id: 3,
        key: "KEEL",
        enabled: true,
        sprint: { id: 7, name: "This month", state: "active" },
        issues: {
          9: {
            id: 9,
            raw: {
              id: 9,
              key: "KEEL-9",
              number: 9,
              title: "Paint",
              type: "story",
              status: "todo",
              priority: "p4",
              assignee_id: 4,
              sprint_id: 7,
            },
          },
        },
      },
    },
  };
}

test("groups sprints by state and keeps the server order", () => {
  const view = planningView({
    library: library(),
    projectId: 3,
    sprints: [
      { id: 8, project_id: 3, name: "Next", goal: "Ship", state: "planned", starts_on: "2026-11-01", ends_on: "2026-11-30" },
      { id: 2, project_id: 3, name: "Last", goal: "", state: "completed", starts_on: "2026-09-01", ends_on: "2026-09-30" },
      { id: 7, project_id: 3, name: "This month", goal: "Focus", state: "active", starts_on: "2026-10-01", ends_on: "2026-10-31" },
    ],
  });
  assert.equal(view.title, "KEEL sprints");
  assert.equal(view.canPlan, true);
  assert.deepEqual(view.sections.map((section) => section.label), ["Planned", "Active", "Completed"]);
  assert.equal(view.sections[0].sprints[0].starts, "2026-11-01");
  assert.equal(view.sections[1].sprints[0].goal, "Focus");
  assert.equal(view.sections[2].sprints[0].name, "Last");
  assert.equal(view.banner, "");
});

test("offline keeps the saved active sprint and marks the other states", () => {
  const view = planningView({ library: library(), projectId: 3, sprints: null });
  assert.match(view.banner, /need a connection/);
  assert.match(view.banner, /saved copy/);
  assert.equal(view.canPlan, false);
  assert.equal(view.sections[0].needsConnection, true);
  assert.equal(view.sections[0].sprints.length, 0);
  assert.equal(view.sections[1].sprints[0].name, "This month");
  assert.equal(view.sections[2].needsConnection, true);
  const detail = sprintDetail({
    library: library(),
    projectId: 3,
    sprint: library().projects[3].sprint,
    online: false,
  });
  assert.equal(detail.editable, false);
  assert.equal(detail.rows[0].key, "KEEL-9");
  assert.equal(detail.rows[0].assignee, "Cursor");
});

test("a waiting issue follows the phone onto the open sprint", () => {
  const stored = library();
  stored.projects[3].issues[9].pending = true;
  stored.projects[3].issues[9].raw.status = "done";
  stored.projects[3].issues[9].raw.sprint_id = 8;
  const detail = sprintDetail({
    library: stored,
    projectId: 3,
    sprint: {
      id: 8,
      name: "Next",
      goal: "",
      state: "planned",
      starts_on: null,
      ends_on: null,
      issues: [],
    },
    online: true,
  });
  assert.equal(detail.canStart, true);
  assert.equal(detail.rows[0].key, "KEEL-9");
  assert.equal(detail.rows[0].statusLabel, "Done");
  assert.equal(detail.rows[0].pending, true);
});

test("the active sprint list drops issues the shared filter does not keep", () => {
  const detail = sprintDetail({
    library: library(),
    projectId: 3,
    sprint: library().projects[3].sprint,
    online: false,
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
  assert.equal(detail.name, "This month");
  assert.equal(detail.rows.length, 0);
});

test("planning checks the name and the dates", () => {
  assert.equal(prepareSprint({ name: "  " }).error, "A sprint needs a name.");
  assert.equal(prepareSprint({ name: "Next", startsOn: "2026-13-01" }).error, "A sprint date could not be read.");
  assert.equal(
    prepareSprint({ name: "Next", startsOn: "2026-11-02", endsOn: "2026-11-01" }).error,
    "A sprint cannot end before it starts.",
  );
  assert.deepEqual(prepareSprint({ name: " Next ", goal: " Ship ", startsOn: "", endsOn: "2026-11-30" }).body, {
    name: "Next",
    goal: "Ship",
    starts_on: null,
    ends_on: "2026-11-30",
  });
});

test("an edit sends only the fields that changed and a blank date clears it", () => {
  const sprint = { name: "Next", goal: "Ship", starts_on: "2026-11-01", ends_on: "2026-11-30" };
  const same = prepareSprintUpdate(sprint, { name: "Next", goal: "Ship", startsOn: "2026-11-01", endsOn: "2026-11-30" });
  assert.deepEqual(same.changes, {});
  const cleared = prepareSprintUpdate(sprint, { name: "Later", goal: "Ship", startsOn: "2026-11-01", endsOn: "" });
  assert.deepEqual(cleared.changes, { name: "Later", ends_on: null });
});

test("completion says where unfinished work went", () => {
  assert.equal(completionNotice({ carried_over: 0 }, []), "No unfinished issues to carry.");
  assert.equal(
    completionNotice({ carried_over: 1, carried_to_sprint_id: null }, []),
    "1 unfinished issue returned to the backlog.",
  );
  assert.equal(
    completionNotice({ carried_over: 2, carried_to_sprint_id: 8 }, [{ id: 8, name: "Next" }]),
    "2 unfinished issues moved to Next.",
  );
});
