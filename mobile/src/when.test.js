const assert = require("node:assert/strict");
const test = require("node:test");

const { formatWhen, monthCells, monthTitle, readWhen, shiftMonth, wrapUnit } = require("./when");

test("a month starts on the weekday of the first and covers every day", () => {
  const cells = monthCells(2026, 9);
  assert.equal(cells[4], 1);
  assert.equal(cells.filter((day) => day !== null).length, 31);
  assert.equal(cells.length % 7, 0);
  assert.equal(monthTitle(2026, 9), "October 2026");
});

test("a chosen date and time formats for the issue form", () => {
  assert.equal(formatWhen({ year: 2026, month: 9, day: 12, hour: 9, minute: 5 }), "2026-10-12 09:05");
  assert.deepEqual(readWhen("2026-10-12 09:05"), {
    year: 2026,
    month: 9,
    day: 12,
    hour: 9,
    minute: 5,
  });
  assert.deepEqual(readWhen("", new Date(2026, 9, 16, 15, 0)), {
    year: 2026,
    month: 9,
    day: 16,
    hour: 9,
    minute: 0,
  });
});

test("the calendar can move to the next month and the clock wraps", () => {
  assert.deepEqual(shiftMonth(2026, 11, 1), { year: 2027, month: 0 });
  assert.equal(wrapUnit(-1, 23), 23);
  assert.equal(wrapUnit(60, 59), 0);
});
