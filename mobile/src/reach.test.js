const assert = require("node:assert/strict");
const test = require("node:test");

const { reachability, reachabilityKnown, setReachable } = require("./reach");

test("a probe marks reachability as known", () => {
  assert.equal(reachabilityKnown(), false);
  setReachable(false);
  assert.equal(reachabilityKnown(), true);
  assert.equal(reachability(), false);
  setReachable(true);
  assert.equal(reachability(), true);
});
