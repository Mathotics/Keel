const assert = require("node:assert/strict");
const test = require("node:test");

const {
  lookupDirty,
  suggestIssues,
  suggestPeople,
  suggestProjects,
} = require("./lookup");

test("project suggestions match a key or name and stay empty until there is text", () => {
  const projects = [
    { id: 3, key: "KEEL", name: "Keel" },
    { id: 4, key: "HULL", name: "Hull" },
  ];
  assert.deepEqual(suggestProjects(projects, ""), []);
  assert.deepEqual(suggestProjects(projects, "hu"), [
    { id: 4, label: "HULL \u2014 Hull" },
  ]);
  assert.equal(suggestProjects(projects, "keel")[0].id, 3);
});

test("people suggestions offer Unassigned and match a name or username", () => {
  const people = [
    { id: 2, display_name: "Jacob Hootman", username: "jbhma" },
    { id: 5, display_name: "Ada", username: "ada" },
  ];
  assert.deepEqual(suggestPeople(people, ""), [{ id: null, label: "Unassigned" }]);
  assert.deepEqual(suggestPeople(people, "jb"), [
    { id: 2, label: "Jacob Hootman" },
  ]);
  assert.equal(suggestPeople(people, "un")[0].label, "Unassigned");
});

test("issue suggestions use the key and title and ignore a blank query", () => {
  const issues = [
    { id: 9, key: "KEEL-9", title: "Paint the hull", type: "story", projectId: 3 },
  ];
  assert.deepEqual(suggestIssues(issues, " "), []);
  const hit = suggestIssues(issues, "paint")[0];
  assert.equal(hit.id, 9);
  assert.equal(hit.label, "KEEL-9 \u2014 Paint the hull");
  assert.equal(hit.type, "story");
});

test("a lookup is unfinished when the text is not the picked value", () => {
  assert.equal(lookupDirty("KEEL \u2014 Keel", "KEEL \u2014 Keel"), false);
  assert.equal(lookupDirty("KEEL \u2014 Keel", "KE"), true);
  assert.equal(lookupDirty("Unassigned", ""), false);
});
