const assert = require("node:assert/strict");
const test = require("node:test");

const {
  blankFilter,
  filterMenus,
  labelOptions,
  matchesIssue,
  sprintOptions,
  toggleChoice,
} = require("./filters");

function issue(overrides) {
  return {
    type: "story",
    status: "todo",
    priority: "p4",
    assignee_id: 4,
    reporter_id: 2,
    sprint_id: 7,
    project_id: 3,
    labels: ["hull"],
    ...overrides,
  };
}

test("a blank filter keeps every type and does not restrict the other fields", () => {
  const filter = blankFilter();
  assert.equal(matchesIssue(issue(), filter), true);
  assert.equal(matchesIssue(issue({ status: "done", priority: "p1", labels: [], assignee_id: null, sprint_id: null }), filter), true);
  const menus = filterMenus(filter, { sprints: [], projects: [], assignees: [], reporters: [], labels: [] }, true);
  assert.deepEqual(menus.map((menu) => menu.title), [
    "Type",
    "Status",
    "Priority",
    "Sprint",
    "Project",
    "Assignee",
    "Created by",
    "Label",
  ]);
  assert.equal(menus[0].summary, "All");
  assert.equal(menus[1].summary, "Any");
  assert.equal(filterMenus(filter, {}, false).some((menu) => menu.title === "Project"), false);
});

test("every chosen filter must match, and one filter accepts any of its values", () => {
  const filter = {
    ...blankFilter(),
    labels: ["hull", "deck"],
    assignees: ["4"],
  };
  assert.equal(matchesIssue(issue({ labels: ["deck"] }), filter), true);
  assert.equal(matchesIssue(issue({ labels: ["sail"] }), filter), false);
  assert.equal(matchesIssue(issue({ assignee_id: 8 }), filter), false);
  assert.equal(matchesIssue(issue({ labels: [] }), { ...blankFilter(), labels: ["unlabeled"] }), true);
  assert.equal(matchesIssue(issue({ assignee_id: null }), { ...blankFilter(), assignees: ["unassigned"] }), true);
  assert.equal(matchesIssue(issue({ reporter_id: null }), { ...blankFilter(), reporters: ["none"] }), true);
  assert.equal(matchesIssue(issue({ sprint_id: null }), { ...blankFilter(), sprints: ["unscheduled"] }), true);
  assert.equal(matchesIssue(issue({ project_id: 8 }), { ...blankFilter(), projects: ["3"] }), false);
  assert.equal(
    matchesIssue(issue({ project_id: 8 }), { ...blankFilter(), projects: ["3"] }, { ignoreProject: true }),
    true,
  );
});

test("clearing every type shows nothing", () => {
  assert.equal(matchesIssue(issue(), { ...blankFilter(), types: [] }), false);
  const next = toggleChoice(blankFilter(), "types", "story");
  assert.deepEqual(next.types, ["epic", "subtask"]);
});

test("sprint choices skip completed sprints and prefix another project's name", () => {
  const library = {
    projects: {
      3: { id: 3, key: "KEEL", enabled: true, sprint: { id: 7, name: "Now", state: "active" } },
      8: { id: 8, key: "DOCS", enabled: true, sprint: { id: 2, name: "Old", state: "completed" } },
    },
  };
  const fetched = [
    { id: 9, name: "Next", state: "planned", projectId: 8, projectKey: "DOCS" },
    { id: 2, name: "Old", state: "completed", projectId: 8, projectKey: "DOCS" },
  ];
  const master = sprintOptions(library, fetched, null);
  assert.deepEqual(master.map(([value]) => value), ["unscheduled", "9", "7"]);
  assert.equal(master[1][1], "DOCS / Next (Planned)");
  assert.equal(master[2][1], "KEEL / Now (Active)");
  assert.deepEqual(sprintOptions(library, fetched, 3).map(([value]) => value), ["unscheduled", "7"]);
});

test("label choices offer unlabeled and names from the catalog and saved issues", () => {
  const options = labelOptions({
    labels: [{ name: "deck" }],
    projects: { 3: { issues: { 9: { raw: { labels: ["hull"] } } } } },
  });
  assert.deepEqual(options.map(([value]) => value), ["unlabeled", "deck", "hull"]);
});
