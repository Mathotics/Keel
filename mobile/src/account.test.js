const assert = require("node:assert/strict");
const test = require("node:test");

const {
  isThisPhone,
  preparePassword,
  preparePerson,
  prepareProfile,
  prepareRename,
} = require("./account");

test("a profile update sends the display name and username", () => {
  const prepared = prepareProfile({ displayName: " Ada ", username: " ada " });
  assert.deepEqual(prepared.body, { display_name: "Ada", username: "ada" });
  assert.equal(prepareProfile({ displayName: " ", username: "ada" }).error, "A user needs a display name.");
  assert.equal(prepareProfile({ displayName: "Ada", username: " " }).error, "A user needs a username.");
});

test("a password change keeps the phone token out of the body", () => {
  const prepared = preparePassword({
    current: "current-secret",
    next: "a-new-secret-1",
    confirm: "a-new-secret-1",
    username: "ada",
  });
  assert.deepEqual(prepared.body, {
    current_password: "current-secret",
    new_password: "a-new-secret-1",
    confirm_password: "a-new-secret-1",
  });
  assert.equal(prepared.body.token, undefined);
  assert.equal(
    preparePassword({ current: "x", next: "short", confirm: "short", username: "ada" }).error,
    "A password must be at least 12 characters.",
  );
  assert.equal(
    preparePassword({ current: "x", next: "a-new-secret-1", confirm: "other-secret-1", username: "ada" }).error,
    "The new passwords do not match.",
  );
});

test("adding someone can leave the username to the display name", () => {
  const prepared = preparePerson({
    displayName: " Morgan ",
    username: "",
    password: "a-new-secret-1",
    confirm: "a-new-secret-1",
  });
  assert.deepEqual(prepared.body, { display_name: "Morgan", password: "a-new-secret-1" });
  assert.equal(prepareRename("  ").error, "A user needs a display name.");
});

test("this phone is the token stored on the device", () => {
  assert.equal(isThisPhone({ id: 9 }, "9"), true);
  assert.equal(isThisPhone({ id: 9 }, 4), false);
});
