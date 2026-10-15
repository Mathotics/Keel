const test = require("node:test");
const assert = require("node:assert/strict");

const { DELETED, NEEDS_CONNECTION, NONE, blankRecipe, prepareRecipe, recipeFromSeries, seriesView } = require("./series");

test("offline schedules ask for a connection and an empty list says so", () => {
  const offline = seriesView({ series: null, online: false });
  assert.equal(offline.banner, NEEDS_CONNECTION);
  assert.equal(offline.rows.length, 0);
  const empty = seriesView({ series: [], online: true });
  assert.equal(empty.empty, NONE);
  const listed = seriesView({
    series: [{ id: 4, title: "Backup", cadence_summary: "Weekly", state: "paused", type: "story" }],
    online: true,
  });
  assert.equal(listed.rows[0].stateLabel, "Paused");
  assert.equal(listed.rows[0].summary, "Weekly");
});

test("a recipe needs a title and a start, and a blank date pair stays unset", () => {
  assert.match(prepareRecipe(blankRecipe()).error, /title/);
  const missingStart = prepareRecipe({ ...blankRecipe(), title: "Backup" });
  assert.match(missingStart.error, /start date/);
  const prepared = prepareRecipe({
    ...blankRecipe(),
    title: " Backup ",
    labels: "Hull, hull",
    startsOn: "2026-10-14",
    freq: "weekly",
    weekdays: [0, 2],
    endMode: "count",
    occurrenceCount: "4",
  });
  assert.equal(prepared.body.title, "Backup");
  assert.deepEqual(prepared.body.labels, ["hull"]);
  assert.deepEqual(prepared.body.weekdays, [0, 2]);
  assert.equal(prepared.body.occurrence_count, 4);
  assert.equal(prepared.body.ends_on, null);
  assert.equal(prepared.body.start_offset_days, null);
  assert.match(prepareRecipe({ ...blankRecipe(), title: "Backup", startsOn: "2026-10-14", startTime: "09:00" }).error, /both a day offset/);
});

test("a saved series fills the recipe and deleting one leaves its issues", () => {
  const draft = recipeFromSeries({
    title: "Backup",
    description: "",
    type: "story",
    priority: "p2",
    labels: ["hull"],
    spawn_mode: "after_closed",
    sprint_basis: "due_on",
    look_ahead_n: 2,
    start_offset_days: 1,
    start_minute_of_day: 540,
    due_offset_days: null,
    due_minute_of_day: null,
    freq: "weekly",
    interval: 1,
    weekdays: "0,2",
    month_day: null,
    nth_week: null,
    month: null,
    starts_on: "2026-10-12",
    ends_on: "2026-12-01",
    occurrence_count: null,
  });
  assert.equal(draft.startTime, "09:00");
  assert.deepEqual(draft.weekdays, [0, 2]);
  assert.equal(draft.endMode, "on");
  assert.equal(draft.priority, "p2");
  assert.equal(DELETED, "Schedule deleted. Existing issues remain.");
});
