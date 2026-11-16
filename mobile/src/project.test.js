const assert = require("node:assert/strict");
const test = require("node:test");

const { prepareProjectUpdate } = require("./project");

test("a project update keeps the key off the body and sends cadence", () => {
  const prepared = prepareProjectUpdate({
    name: " Keel ",
    description: " Tracker ",
    cadence: "weekly",
    days: "",
    ahead: "2",
  });
  assert.deepEqual(prepared.body, {
    name: "Keel",
    description: "Tracker",
    sprint_cadence: "weekly",
    sprint_ahead: 2,
  });
  assert.equal(prepared.body.key, undefined);
});

test("every N days requires a positive day count", () => {
  const missing = prepareProjectUpdate({
    name: "Keel",
    description: "",
    cadence: "every_n_days",
    days: "",
    ahead: "0",
  });
  assert.equal(missing.error, "Every N days needs a number of days of at least 1.");
  const prepared = prepareProjectUpdate({
    name: "Keel",
    description: "",
    cadence: "every_n_days",
    days: "10",
    ahead: "0",
  });
  assert.equal(prepared.body.sprint_cadence_days, 10);
});

test("currency has to be an ISO code the project can use", () => {
  const saved = prepareProjectUpdate({
    name: "Keel",
    description: "",
    cadence: "off",
    days: "",
    ahead: "0",
    currency: "jpy",
  });
  assert.equal(saved.body.currency, "JPY");
  const refused = prepareProjectUpdate({
    name: "Keel",
    description: "",
    cadence: "off",
    days: "",
    ahead: "0",
    currency: "XYZ",
  });
  assert.equal(refused.error, "Currency must be an ISO code such as USD.");
});

test("a blank name and an out of range ahead are refused", () => {
  assert.equal(
    prepareProjectUpdate({ name: " ", description: "", cadence: "off", days: "", ahead: "0" }).error,
    "A project needs a name.",
  );
  assert.equal(
    prepareProjectUpdate({ name: "Keel", description: "", cadence: "off", days: "", ahead: "13" }).error,
    "Sprints in advance must be a whole number from 0 to 12.",
  );
});
