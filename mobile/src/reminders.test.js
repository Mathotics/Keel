const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  absorbRules,
  chooseReminderPhone,
  deleteRule,
  planFires,
  putRule,
  reminderIsOn,
  retargetIssue,
  uploadReminderQueue,
} = require("./reminders");

const cases = JSON.parse(
  fs.readFileSync(path.join(__dirname, "../../tests/fixtures/reminder_clock.json"), "utf8"),
);

function storeWith(reminders) {
  return { projects: {}, people: [], labels: [], queue: [], reminders };
}

test("the phone clock matches the shared reminder cases", () => {
  cases.forEach((entry) => {
    const fires = planFires(entry);
    assert.deepEqual(fires, entry.fires, entry.name);
  });
});

test("a pending phone rule survives a server refresh", () => {
  const saved = putRule(storeWith(null), "issue", { issueId: 7 }, { at_due: true }, "2026-11-18T09:00:00");
  const absorbed = absorbRules(saved, {
    default: null,
    series: [],
    issues: [{ issue_id: 7, at_due: false, updated_at: "2026-11-18T08:00:00" }],
    states: [],
  });
  assert.equal(absorbed.reminders.issueRules[0].pending, true);
  assert.equal(absorbed.reminders.issueRules[0].at_due, true);
});

test("uploading a local issue retargets its reminder", () => {
  const saved = putRule(storeWith(null), "issue", { issueId: -3 }, { at_due: true }, "2026-11-18T09:00:00");
  const moved = retargetIssue(saved, -3, 41);
  assert.equal(moved.reminders.issueRules[0].issue_id, 41);
  assert.equal(moved.reminders.queue[0].path, "/api/v1/issues/41/reminder");
});

test("turning off a reminder that was never uploaded does not call the server", () => {
  const saved = putRule(storeWith(null), "default", {}, { at_due: true }, "2026-11-18T09:00:00");
  const cleared = deleteRule(saved, "default", {});
  assert.equal(cleared.reminders.defaultRule, null);
  assert.equal(cleared.reminders.queue.length, 0);
});

test("an issue shows reminders on only when its effective rule would fire", () => {
  const quiet = { projects: {}, people: [], labels: [], queue: [] };
  assert.equal(reminderIsOn({ id: 7, series_id: null }, quiet.reminders), false);
  const inherited = putRule(quiet, "default", {}, { at_due: true }, "2026-11-18T09:00:00");
  assert.equal(reminderIsOn({ id: 7, series_id: null }, inherited.reminders), true);
  const own = putRule(inherited, "issue", { issueId: 7 }, { at_start: false, at_due: false }, "2026-11-18T09:05:00");
  assert.equal(reminderIsOn({ id: 7, series_id: null }, own.reminders), false);
});

test("a conflict keeps the phone copy until the person picks the server stamp", async () => {
  const saved = putRule(storeWith(null), "default", {}, { at_due: true }, "2026-11-18T09:00:00");
  saved.reminders.defaultRule.pending = false;
  saved.reminders.defaultRule.updated_at = "2026-11-18T08:00:00";
  saved.reminders.queue = [];
  const edited = putRule(saved, "default", {}, { at_start: true }, "2026-11-18T09:30:00");
  const client = {
    async send() {
      const error = new Error("conflict");
      error.status = 409;
      error.body = {
        detail: {
          context: { server: { at_due: true, updated_at: "2026-11-18T09:15:00" } },
        },
      };
      throw error;
    },
  };
  const conflicted = await uploadReminderQueue(edited, client);
  const item = conflicted.reminders.queue[0];
  assert.equal(item.conflict.updated_at, "2026-11-18T09:15:00");
  const chosen = chooseReminderPhone(conflicted, item.id);
  assert.equal(chosen.reminders.queue[0].conflict, null);
  assert.equal(chosen.reminders.queue[0].body.base_updated_at, "2026-11-18T09:15:00");
  assert.equal(chosen.reminders.defaultRule.at_start, true);
});
