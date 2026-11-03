const assert = require("node:assert/strict");
const test = require("node:test");

const { bareAmount, labeledAmount, sameAmount } = require("../../assets/js/money");

test("editing a cost field keeps the number and drops the unit", () => {
  assert.equal(bareAmount("$1,234.56 USD"), "1234.56");
  assert.equal(bareAmount("¥12.40 JPY"), "12.40");
  assert.equal(bareAmount("R$12.50 BRL"), "12.50");
  assert.equal(bareAmount("12.50 XXX"), "12.50");
  assert.equal(labeledAmount("12.5", "$", "USD"), "$12.50 USD");
  assert.equal(labeledAmount("12.4", "¥", "JPY"), "¥12.40 JPY");
  assert.equal(labeledAmount("", "$", "USD"), "");
  assert.equal(sameAmount("12.5", "$12.50 USD"), true);
  assert.equal(sameAmount("0.00", "$0.00 USD"), true);
  assert.equal(sameAmount("", "$0.00 USD"), false);
  assert.equal(sameAmount("15", "$12.50 USD"), false);
});
