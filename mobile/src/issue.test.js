const assert = require("node:assert/strict");
const test = require("node:test");

const { formatMinutes, formatWhen, issueKeyParts, issuePage, linkEnds, parseMarkdown, savedIssueId } = require("./issue");

test("formats effort the way the server does", () => {
  assert.equal(formatMinutes(null), "None");
  assert.equal(formatMinutes(0), "0m");
  assert.equal(formatMinutes(90), "1h 30m");
  assert.equal(formatMinutes(480), "1d");
});

test("shows timestamps in UTC", () => {
  assert.equal(formatWhen(null), "None");
  assert.equal(formatWhen("2026-10-11T16:05:00"), "2026-10-11 16:05 UTC");
});

test("reads headings, lists, emphasis, and code", () => {
  const blocks = parseMarkdown("# Title\n\nA **bold** note.\n\n- One\n- Two\n\n```\ncode\n```");
  assert.equal(blocks[0].type, "heading");
  assert.equal(blocks[1].inlines[1].bold, true);
  assert.equal(blocks[2].type, "list");
  assert.equal(blocks[2].items.length, 2);
  assert.equal(blocks[3].type, "code");
  assert.equal(blocks[3].text, "code");
  assert.deepEqual(parseMarkdown("  "), []);
});

test("assembles a read-only issue page", () => {
  const page = issuePage({
    issue: {
      id: 9,
      key: "KEEL-9",
      title: "Paint",
      type: "story",
      status: "todo",
      priority: "p3",
      assignee_id: 2,
      reporter_id: null,
      labels: ["hull"],
      start_at: null,
      due_at: "2026-10-12T15:00:00",
      created_at: "2026-10-01T12:00:00",
      updated_at: "2026-10-02T12:00:00",
      estimate_minutes: 60,
      remaining_minutes: null,
      description: "Sand the **bow**.",
      definition_of_done: "- Two **even** coats.",
      rollup: {
        estimate_minutes: 120,
        remaining_minutes: 60,
        descendants: 2,
        descendants_done: 1,
        descendants_cancelled: 0,
      },
    },
    users: [{ id: 2, display_name: "Jacob Hootman" }],
    parent: { id: 1, key: "KEEL-1", title: "Restore" },
    children: [{ id: 10, key: "KEEL-10", title: "Sand", status: "done" }],
    dependencies: {
      blocks: [],
      blocked_by: [{ id: 3, dependency_id: 9, key: "BOAT-2", title: "Haul out", project_key: "BOAT" }],
      relates_to: [{ id: 4, dependency_id: 10, key: "KEEL-4", title: "Same project", project_key: "KEEL" }],
    },
    history: [
      {
        created_at: "2026-10-02T12:00:00",
        actor_name: "Jacob Hootman",
        field: "title",
        from_value: "Old",
        to_value: "Paint",
      },
    ],
    historyAvailable: true,
    sprint: { name: "This week" },
    comments: [
      {
        id: 4,
        author_id: 2,
        body: "Sand the **bow**.",
        created_at: "2026-10-12T15:04:00",
      },
    ],
  });
  assert.equal(page.assignee, "Jacob Hootman");
  assert.equal(page.reporter, "None");
  assert.equal(page.priorityLabel, "P3 — Major");
  assert.equal(page.estimate, "1h");
  assert.equal(page.rollup.progress, "1 of 2 done");
  assert.equal(page.parent.key, "KEEL-1");
  assert.equal(page.children[0].statusLabel, "Done");
  assert.equal(page.blockedBy[0].projectKey, "BOAT");
  assert.equal(page.blockedBy[0].dependencyId, 9);
  assert.equal(page.relatesTo[0].projectKey, null);
  assert.match(page.history[0], /title Old → Paint/);
  assert.equal(page.sprintName, "This week");
  assert.equal(page.comments[0].author, "Jacob Hootman");
  assert.equal(page.comments[0].blocks[0].inlines[1].bold, true);
  assert.equal(page.definitionOfDoneText, "- Two **even** coats.");
  assert.equal(page.definitionOfDone[0].type, "list");
  assert.equal(page.definitionOfDone[0].items[0][1].bold, true);
});

test("an issue with no definition of done renders nothing for it", () => {
  const page = issuePage({ issue: { id: 1, key: "KEEL-1", title: "Paint" }, users: [] });
  assert.equal(page.definitionOfDoneText, "");
  assert.deepEqual(page.definitionOfDone, []);
});

test("a link points the right way and a key finds a saved issue", () => {
  assert.deepEqual(issueKeyParts(" keel-12 "), { key: "KEEL", number: 12 });
  assert.equal(issueKeyParts("nope"), null);
  assert.deepEqual(linkEnds(9, 3, "blocks"), { source_id: 9, target_id: 3, kind: "blocks" });
  assert.deepEqual(linkEnds(9, 3, "blocked_by"), { source_id: 3, target_id: 9, kind: "blocks" });
  assert.deepEqual(linkEnds(9, 3, "relates_to"), { source_id: 9, target_id: 3, kind: "relates_to" });
  const library = {
    projects: {
      8: { issues: { 3: { raw: { id: 3, key: "BOAT-2" } } } },
      3: { issues: { "-1": { raw: { id: -1, key: "KEEL-9" } } } },
    },
  };
  assert.equal(savedIssueId(library, "boat-2"), 3);
  assert.equal(savedIssueId(library, "KEEL-9"), null);
});
