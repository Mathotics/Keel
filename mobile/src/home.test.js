const assert = require("node:assert/strict");
const test = require("node:test");

const {
  ALL_HIDDEN,
  arrangeInbox,
  blankLayout,
  hideSection,
  moveSection,
  parseLayout,
  showSection,
} = require("./home");

function view() {
  return {
    empty: "",
    banner: "",
    sections: [
      { key: "due", title: "Due or overdue", rows: [{ id: 1 }] },
      { key: "assigned", title: "Assigned to me", rows: [{ id: 1 }] },
      { key: "blocked", title: "Blocked", rows: [{ id: 1 }] },
    ],
  };
}

test("a missing arrangement is the default stack with nothing removed", () => {
  const layout = parseLayout(null);
  assert.equal(layout.hidden.length, 0);
  assert.equal(layout.order[0], "now");
  assert.equal(layout.order[layout.order.length - 1], "completed");
  const arranged = arrangeInbox(view(), layout);
  assert.deepEqual(arranged.sections.map((section) => section.key), ["due", "assigned", "blocked"]);
  assert.equal(arranged.hidden.length, 0);
});

test("remove keeps a panel off the page and add puts it at the end", () => {
  const hidden = hideSection(blankLayout(), "assigned");
  const removed = arrangeInbox(view(), hidden);
  assert.deepEqual(removed.sections.map((section) => section.key), ["due", "blocked"]);
  assert.deepEqual(removed.hidden, [{ key: "assigned", title: "Assigned to me" }]);
  const restored = showSection(hidden, "assigned");
  assert.equal(restored.order[restored.order.length - 1], "assigned");
  assert.equal(restored.hidden.includes("assigned"), false);
  const stillEmpty = arrangeInbox(
    { empty: "", sections: [{ key: "due", title: "Due or overdue", rows: [{ id: 1 }] }] },
    restored,
  );
  assert.deepEqual(stillEmpty.sections.map((section) => section.key), ["due"]);
});

test("up and down swap rendered panels and leave an empty panel in its slot", () => {
  const layout = blankLayout();
  const visible = ["due", "assigned"];
  const moved = moveSection(layout, visible, "assigned", "up");
  assert.equal(moved.order[0], "now");
  assert.equal(moved.order[1], "assigned");
  assert.equal(moved.order[2], "week");
  assert.equal(moved.order[5], "due");
  const stuck = moveSection(moved, ["assigned", "due"], "assigned", "up");
  assert.equal(stuck.order[0], "now");
  assert.equal(stuck.order[1], "assigned");
  assert.equal(stuck.order[5], "due");
  const arranged = arrangeInbox(view(), moved);
  assert.deepEqual(arranged.sections.map((section) => section.key), ["assigned", "due", "blocked"]);
});

test("hiding every panel that has rows says so", () => {
  let layout = blankLayout();
  for (const key of ["due", "assigned", "blocked"]) {
    layout = hideSection(layout, key);
  }
  const arranged = arrangeInbox(view(), layout);
  assert.equal(arranged.sections.length, 0);
  assert.equal(arranged.allHidden, ALL_HIDDEN);
  assert.equal(arranged.empty, "");
  assert.equal(arrangeInbox({ empty: "Nothing is assigned to you.", sections: [] }, layout).allHidden, "");
});

test("a saved arrangement drops unknown keys and keeps a new panel", () => {
  const layout = parseLayout(JSON.stringify({
    order: ["blocked", "nope", "due"],
    hidden: ["week", "missing"],
  }));
  assert.equal(layout.hidden.includes("week"), true);
  assert.equal(layout.hidden.includes("missing"), false);
  assert.equal(layout.order[0], "blocked");
  assert.equal(layout.order.includes("assigned"), true);
  assert.equal(layout.order.includes("week"), false);
  assert.equal(parseLayout("{").order[0], "now");
});
