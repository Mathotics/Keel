const assert = require("node:assert/strict");
const test = require("node:test");

const { applyPasswordEdit, maskPassword } = require("./password");

test("shows only the last character", () => {
  assert.equal(maskPassword(""), "");
  assert.equal(maskPassword("a"), "a");
  assert.equal(maskPassword("ab"), "\u2022b");
  assert.equal(maskPassword("abc"), "\u2022\u2022c");
});

test("appends, deletes, and replaces through the masked field", () => {
  assert.equal(applyPasswordEdit("abc", "\u2022\u2022cd"), "abcd");
  assert.equal(applyPasswordEdit("abc", "\u2022\u2022"), "ab");
  assert.equal(applyPasswordEdit("abc", ""), "");
  assert.equal(applyPasswordEdit("abc", "z"), "z");
  assert.equal(applyPasswordEdit("abc", "\u2022\u2022d"), "abd");
});
