const assert = require("node:assert/strict");
const test = require("node:test");

const {
  EMPTY,
  PHONE_NOTE,
  appBarSlots,
  bellState,
  mergeInbox,
  noticeList,
  openNotice,
  preferenceBody,
  preferenceRows,
  togglePreference,
  viewedNotices,
  withoutNotice,
} = require("./notifications");

test("the bell sits between the connection mark and the profile initials", () => {
  const slots = appBarSlots();
  assert.ok(slots.indexOf("connection") < slots.indexOf("bell"));
  assert.ok(slots.indexOf("bell") < slots.indexOf("profile"));
  assert.equal(slots.filter((slot) => slot === "bell").length, 1);
});

test("the unread dot is on only when a notice is unread and has no count", () => {
  const quiet = bellState([{ id: 1, read_at: "2026-11-11T00:00:00" }]);
  assert.equal(quiet.dot, false);
  assert.equal(quiet.label, "Notifications");
  assert.equal("count" in quiet, false);

  const waiting = bellState([
    { id: 1, read_at: "2026-11-11T00:00:00" },
    { id: 2, read_at: null },
  ]);
  assert.equal(waiting.dot, true);
  assert.equal(waiting.label, "Notifications, unread");
  assert.equal(bellState([]).dot, false);
});

test("the list is newest first, unread looks different, and empty says so", () => {
  const list = noticeList([
    { id: 1, created_at: "2026-11-01T00:00:00", issue_key: "KEEL-1", issue_title: "Older", body: "First", actor_name: "Ada", read_at: null },
    { id: 2, created_at: "2026-11-08T00:00:00", issue_key: "KEEL-2", issue_title: "Newer", body: "Second", actor_name: "Bea", read_at: "2026-11-08T01:00:00" },
  ]);
  assert.deepEqual(list.rows.map((row) => row.issueTitle), ["Newer", "Older"]);
  assert.equal(list.rows[0].unread, false);
  assert.equal(list.rows[1].unread, true);
  assert.equal(noticeList([]).empty, EMPTY);
  assert.equal(noticeList([]).rows.length, 0);
});

test("opening one notice marks it read and opens the issue when it still exists", () => {
  const opened = openNotice({ id: 4, issue_id: 12, issue_key: "KEEL-3", issue_title: "Hull" });
  assert.deepEqual(opened.readIds, [4]);
  assert.equal(opened.issueId, 12);
  const shown = noticeList([{ id: 4, issue_id: 12, issue_key: "KEEL-3", issue_title: "Hull" }]).rows[0];
  assert.equal(openNotice(shown).issueId, 12);

  const deleted = openNotice({ id: 5, issue_id: null, issue_key: "KEEL-9", issue_title: "Gone" });
  assert.equal(deleted.issueId, null);
  const row = noticeList([{
    id: 5,
    issue_id: null,
    issue_key: "KEEL-9",
    issue_title: "Gone",
    body: "Removed",
    actor_name: "Ada",
  }]).rows[0];
  assert.equal(row.heading, "KEEL-9 Gone");
  assert.equal(row.body, "Removed");
  assert.equal(row.linked, false);
});

test("viewing the list marks every unread notice read and delete removes one", () => {
  const notices = [
    { id: 1, read_at: null },
    { id: 2, read_at: "2026-11-01T00:00:00" },
    { id: 3, read_at: null },
  ];
  assert.deepEqual(viewedNotices(notices), [1, 3]);
  assert.deepEqual(withoutNotice(notices, 1).map((notice) => notice.id), [2, 3]);
});

test("the preference grid keeps any combination and names each event", () => {
  const rows = preferenceRows([
    { type: "assigned", email: true, phone: false, bell: false },
  ]);
  assert.equal(rows.length, 7);
  assert.equal(rows[0].label, "Comment on an issue you created");
  assert.equal(rows[0].bell, true);
  assert.equal(rows[0].email, false);
  const assigned = rows.find((row) => row.type === "assigned");
  assert.equal(assigned.label, "Someone assigns an issue to you");
  assert.equal(assigned.email, true);
  assert.equal(assigned.bell, false);
  const toggled = togglePreference(rows, "comment_on_created", "phone");
  assert.equal(toggled[0].phone, true);
  assert.equal(rows[0].phone, false);
  const body = preferenceBody(toggled);
  assert.equal(body.preferences.length, 7);
  assert.equal(body.preferences[0].phone, true);
  assert.equal(body.preferences[2].email, true);
  assert.match(PHONE_NOTE, /Android notification is sent in a later update/);
});

test("an offline list stays until the server copy replaces it", () => {
  const cached = [{ id: 1, body: "Saved" }];
  const server = [{ id: 2, body: "Live" }];
  assert.deepEqual(mergeInbox(cached, server, false), cached);
  assert.deepEqual(mergeInbox(cached, server, true), server);
  assert.deepEqual(mergeInbox(cached, null, true), cached);
});
