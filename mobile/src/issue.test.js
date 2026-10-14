const assert = require("node:assert/strict");
const test = require("node:test");

const { formatMinutes, formatWhen, issuePage, parseMarkdown } = require("./issue");

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
      blocked_by: [{ id: 3, key: "BOAT-2", title: "Haul out", project_key: "BOAT" }],
      relates_to: [],
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
  assert.match(page.history[0], /title Old → Paint/);
  assert.equal(page.sprintName, "This week");
  assert.equal(page.comments[0].author, "Jacob Hootman");
  assert.equal(page.comments[0].blocks[0].inlines[1].bold, true);
});
