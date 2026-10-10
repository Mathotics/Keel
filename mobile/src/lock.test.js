const assert = require("node:assert/strict");
const test = require("node:test");

const { ALWAYS, ON_LAUNCH, ON_RESUME, shouldUnlock } = require("./lock");

test("stays open when signed out, unlocked, or the phone has no lock", () => {
  for (const setting of [ALWAYS, ON_LAUNCH, ON_RESUME]) {
    assert.equal(
      shouldUnlock({
        signedIn: false,
        setting,
        hasDeviceLock: true,
        event: "launch",
      }),
      false,
    );
    assert.equal(
      shouldUnlock({
        signedIn: true,
        setting,
        hasDeviceLock: false,
        event: "launch",
      }),
      false,
    );
  }
  assert.equal(
    shouldUnlock({
      signedIn: true,
      setting: ALWAYS,
      hasDeviceLock: true,
      event: "resume",
    }),
    false,
  );
});

test("asks on a cold start for the closed and switching settings", () => {
  const base = { signedIn: true, hasDeviceLock: true, event: "launch" };
  assert.equal(shouldUnlock({ ...base, setting: ON_LAUNCH }), true);
  assert.equal(shouldUnlock({ ...base, setting: ON_RESUME }), true);
});

test("asks after switching only for that setting", () => {
  const base = { signedIn: true, hasDeviceLock: true, event: "resume" };
  assert.equal(shouldUnlock({ ...base, setting: ON_RESUME }), true);
  assert.equal(shouldUnlock({ ...base, setting: ON_LAUNCH }), false);
});
