const assert = require("node:assert/strict");
const test = require("node:test");

const { phoneDelivery, phoneSetup, pushIsFresh, pushIssueId } = require("./phone");

test("firebase registers the phone and ntfy keeps the subscribe address", () => {
  assert.deepEqual(phoneSetup({ provider: "fcm" }), { mode: "fcm", subscribeUrl: "" });
  assert.deepEqual(phoneSetup({ provider: "ntfy", subscribe_url: " http://ntfy.local/topic " }), {
    mode: "ntfy",
    subscribeUrl: "http://ntfy.local/topic",
  });
  assert.equal(phoneSetup({ provider: "" }).mode, "off");
  assert.match(phoneDelivery(phoneSetup({ provider: "fcm" })), /Firebase/);
  assert.match(phoneDelivery(phoneSetup({ provider: "ntfy", subscribe_url: "http://ntfy.local/t" })), /ntfy app/);
  assert.match(phoneDelivery(phoneSetup(null)), /until a provider/);
});

test("a fresh push opens the issue and an old one does not", () => {
  const response = {
    notification: {
      date: 1_000,
      request: { content: { data: { issueId: "12" } } },
    },
  };
  assert.equal(pushIssueId(response), 12);
  assert.equal(pushIsFresh(response, 1_000 + 1_000), true);
  assert.equal(pushIsFresh(response, 1_000 + 20_000), false);
  assert.equal(pushIssueId({ notification: { request: { content: { data: { issueId: "" } } } } }), null);
});
