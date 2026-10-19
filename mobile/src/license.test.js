const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const { LICENSE_TEXT } = require("./license");

test("the phone shows the same license text as the project", () => {
  const file = fs.readFileSync(path.join(__dirname, "..", "..", "LICENSE"), "utf8");
  assert.equal(LICENSE_TEXT.replace(/\r\n/g, "\n"), file.replace(/\r\n/g, "\n"));
});
