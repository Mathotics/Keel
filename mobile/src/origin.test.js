const assert = require("node:assert/strict");
const test = require("node:test");

const {
  EMPTY,
  INVALID,
  healthUrl,
  isConnected,
  parseOrigin,
} = require("./origin");

test("rejects an empty address", () => {
  assert.deepEqual(parseOrigin("   "), { ok: false, message: EMPTY });
});

test("accepts an http origin and trims a trailing slash", () => {
  assert.deepEqual(parseOrigin("http://192.168.1.122:8000/"), {
    ok: true,
    origin: "http://192.168.1.122:8000",
  });
});

test("accepts an https origin without a port", () => {
  assert.deepEqual(parseOrigin("https://keel.example"), {
    ok: true,
    origin: "https://keel.example",
  });
});

test("rejects a path, query, scheme, or missing host", () => {
  for (const value of [
    "http://192.168.1.122:8000/health",
    "http://192.168.1.122:8000?x=1",
    "ftp://192.168.1.122",
    "192.168.1.122:8000",
    "http://",
  ]) {
    assert.equal(parseOrigin(value).ok, false);
    assert.equal(parseOrigin(value).message, INVALID);
  }
});

test("builds the health url from the origin only", () => {
  assert.equal(healthUrl("http://100.83.123.25:8000"), "http://100.83.123.25:8000/health");
});

test("treats only status ok as connected", () => {
  assert.equal(isConnected({ status: "ok" }), true);
  assert.equal(isConnected({ status: "down" }), false);
  assert.equal(isConnected(null), false);
  assert.equal(isConnected("ok"), false);
});
