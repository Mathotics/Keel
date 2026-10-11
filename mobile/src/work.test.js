const assert = require("node:assert/strict");
const test = require("node:test");

const { activeSprint, statusLabel, workSection } = require("./work");

test("names the workflow statuses", () => {
  assert.equal(statusLabel("todo"), "To Do");
  assert.equal(statusLabel("in_progress"), "In Progress");
  assert.equal(statusLabel("cancelled"), "Cancelled");
});

test("keeps only the active sprint", () => {
  const sprints = [
    { id: 1, state: "completed", name: "Last month" },
    { id: 2, state: "planned", name: "Next month" },
    { id: 3, state: "active", name: "This month" },
  ];
  assert.equal(activeSprint(sprints).id, 3);
  assert.equal(activeSprint([{ id: 1, state: "planned" }]), null);
});

test("builds a project section from the active sprint only", () => {
  const project = { id: 3, key: "KEEL", name: "Keel Software Development" };
  const sprints = [{ id: 7, state: "active", name: "1 Oct – 1 Nov 2026" }];
  const detail = {
    id: 7,
    state: "active",
    issues: [{ id: 258, key: "KEEL-71", title: "Show projects", status: "in_progress" }],
  };
  const section = workSection(project, sprints, detail);
  assert.equal(section.sprintName, "1 Oct – 1 Nov 2026");
  assert.deepEqual(section.issues, [
    {
      id: 258,
      key: "KEEL-71",
      title: "Show projects",
      status: "in_progress",
      statusLabel: "In Progress",
    },
  ]);
});

test("drops issues when the project has no active sprint", () => {
  const project = { id: 1, key: "HOUSE", name: "House Chores" };
  const section = workSection(
    project,
    [{ id: 4, state: "planned", name: "Later" }],
    { id: 4, state: "planned", issues: [{ id: 1, key: "HOUSE-1", title: "Paint", status: "todo" }] },
  );
  assert.equal(section.sprintName, null);
  assert.deepEqual(section.issues, []);
});
