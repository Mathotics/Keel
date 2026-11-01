const assert = require("node:assert/strict");
const test = require("node:test");

const {
  BACK_EDGE,
  claimsMenuDismiss,
  claimsPageBack,
  notePhase,
  releasesMenuDismiss,
  releasesPageBack,
} = require("./swipe");

test("a left swipe still claims and releases the menu", () => {
  const claim = { dx: -24, dy: 4 };
  assert.equal(claimsMenuDismiss(claim), true);
  assert.equal(releasesMenuDismiss({ dx: -48, vx: 0 }), true);
  assert.equal(releasesMenuDismiss({ dx: -10, vx: -0.4 }), true);
});

test("a right swipe does not dismiss the menu", () => {
  assert.equal(claimsMenuDismiss({ dx: 40, dy: 0 }), false);
  assert.equal(releasesMenuDismiss({ dx: 80, vx: 0.8 }), false);
});

test("a mostly vertical drag does not claim the menu", () => {
  assert.equal(claimsMenuDismiss({ dx: -30, dy: -40 }), false);
});

test("a right swipe from the left edge goes back", () => {
  assert.equal(claimsPageBack({ x0: 8, dx: 12, dy: 2 }), true);
  assert.equal(claimsPageBack({ x0: BACK_EDGE, dx: 20, dy: 4 }), true);
  assert.equal(releasesPageBack({ dx: 48, vx: 0 }), true);
  assert.equal(releasesPageBack({ dx: 16, vx: 0.4 }), true);
});

test("the same right swipe away from the edge does not go back", () => {
  assert.equal(claimsPageBack({ x0: BACK_EDGE + 1, dx: 80, dy: 0 }), false);
});

test("a left swipe does not go back a page", () => {
  assert.equal(claimsPageBack({ x0: 4, dx: -40, dy: 0 }), false);
  assert.equal(releasesPageBack({ dx: -80, vx: -1 }), false);
});

test("a vertical drag on the edge does not go back", () => {
  assert.equal(claimsPageBack({ x0: 4, dx: 16, dy: 30 }), false);
});

test("opening a page remembers the one that was showing", () => {
  const opened = notePhase([], "home", "projects", false);
  assert.deepEqual(opened.history, ["home"]);
  const nested = notePhase(opened.history, "projects", "issue", false);
  assert.deepEqual(nested.history, ["home", "projects"]);
});

test("returning to the recorded page drops it from the stack", () => {
  const back = notePhase(["home", "projects"], "issue", "projects", false);
  assert.deepEqual(back.history, ["home"]);
});

test("a back navigation does not record the page being left", () => {
  const back = notePhase(["home"], "issue", "home", true);
  assert.deepEqual(back.history, ["home"]);
  assert.equal(back.restoring, false);
});

test("signing out clears the page stack", () => {
  const signedOut = notePhase(["home", "projects"], "settings", "signedOut", false);
  assert.deepEqual(signedOut.history, []);
});
