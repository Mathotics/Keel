const assert = require("node:assert/strict");
const test = require("node:test");

const { ENTER_QUERY, NEEDS_CONNECTION, findView } = require("./find");

function library() {
  return {
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
              title: "Paint the door",
              description: "Use the blue paint",
              sprint_id: 7,
            },
            page: { comments: [{ body: "the hinge is stuck" }] },
          },
          10: {
            id: 10,
            raw: {
              id: 10,
              key: "KEEL-10",
              number: 10,
              title: "Backlog paint",
              description: "",
              sprint_id: null,
            },
          },
        },
      },
    },
  };
}

test("an empty query asks for text", () => {
  const view = findView({ library: library(), query: "  ", payload: null });
  assert.equal(view.prompt, ENTER_QUERY);
  assert.equal(view.sections.length, 0);
  assert.equal(view.jump, null);
});

test("an exact saved key jumps and other saved matches stay listed", () => {
  const jump = findView({ library: library(), query: "keel-9", payload: null });
  assert.equal(jump.jump.target, "issue");
  assert.equal(jump.jump.issueId, 9);
  const listed = findView({ library: library(), query: "paint", payload: null });
  assert.equal(listed.banner, NEEDS_CONNECTION);
  assert.deepEqual(listed.sections[0].rows.map((row) => row.title), ["KEEL-9"]);
  assert.equal(listed.sections[1].needsConnection, true);
  const comment = findView({ library: library(), query: "hinge", payload: null });
  assert.equal(comment.sections[0].rows[0].snippet.includes("hinge"), true);
});

test("server results list every kind and a user jump stays on the list", () => {
  const listed = findView({
    library: library(),
    query: "door",
    payload: {
      kind: "results",
      query: "door",
      issues: [{ id: 9, key: "KEEL-9", title: "Paint the door", project_key: "KEEL", snippet: null }],
      issues_more: true,
      projects: [{ id: 3, key: "KEEL", name: "Keel", snippet: null }],
      projects_more: false,
      sprints: [{ id: 7, name: "This month", project_id: 3, project_key: "KEEL", snippet: null }],
      sprints_more: false,
      users: [{ display_name: "Cursor" }],
      users_more: false,
    },
  });
  assert.equal(listed.banner, "");
  assert.equal(listed.sections[0].rows[0].title, "KEEL-9");
  assert.match(listed.sections[0].more, /More issues/);
  assert.equal(listed.sections[2].rows[0].projectId, 3);
  assert.equal(listed.sections[3].rows[0].title, "Cursor");
  const user = findView({
    library: library(),
    query: "Cursor",
    payload: { kind: "jump", target: "user", display_name: "Cursor" },
  });
  assert.equal(user.jump, null);
  assert.equal(user.sections[0].rows[0].title, "Cursor");
  const issue = findView({
    library: library(),
    query: "KEEL-12",
    payload: { kind: "jump", target: "issue", issue_id: 12, project_id: 3, key: "KEEL-12" },
  });
  assert.equal(issue.jump.issueId, 12);
});
