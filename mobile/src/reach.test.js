const assert = require("node:assert/strict");
const test = require("node:test");

const {
  connectionMode,
  forcedOffline,
  reachability,
  reachabilityKnown,
  setForcedOffline,
  setReachable,
  shouldStayOffline,
} = require("./reach");

test("a probe marks reachability as known", () => {
  assert.equal(reachabilityKnown(), false);
  setReachable(false);
  assert.equal(reachabilityKnown(), true);
  assert.equal(reachability(), false);
  setReachable(true);
  assert.equal(reachability(), true);
});

test("three connection modes stay distinct, and a lock ignores a live server", () => {
  assert.equal(connectionMode(true, false), "online");
  assert.equal(connectionMode(false, false), "offline");
  assert.equal(connectionMode(true, true), "locked");
  setReachable(true);
  setForcedOffline(true);
  assert.equal(forcedOffline(), true);
  assert.equal(reachability(), true);
  assert.equal(shouldStayOffline({
    known: reachabilityKnown(),
    online: reachability(),
    forced: forcedOffline(),
  }), true);
  setForcedOffline(false);
  assert.equal(shouldStayOffline({
    known: true,
    online: true,
    forced: false,
  }), false);
  assert.equal(shouldStayOffline({
    known: true,
    online: false,
    forced: false,
  }), true);
});
