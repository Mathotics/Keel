const FRESH_MS = 15000;

function phoneSetup(payload) {
  const provider = payload && payload.provider;
  if (provider === "fcm") {
    return { mode: "fcm", subscribeUrl: "" };
  }
  if (provider === "ntfy") {
    return { mode: "ntfy", subscribeUrl: String((payload && payload.subscribe_url) || "").trim() };
  }
  return { mode: "off", subscribeUrl: "" };
}

function phoneDelivery(setup) {
  if (setup && setup.mode === "ntfy" && setup.subscribeUrl) {
    return "Subscribe to this topic in the ntfy app.";
  }
  if (setup && setup.mode === "fcm") {
    return "Open Keel on the phone so it can register for Firebase alerts.";
  }
  return "The server sends nothing until a provider is configured.";
}

function pushIssueId(response) {
  const data = response
    && response.notification
    && response.notification.request
    && response.notification.request.content
    && response.notification.request.content.data;
  const raw = data && (data.issueId || data.issue_id);
  const id = Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

function pushIsFresh(response, now) {
  const date = response && response.notification && response.notification.date;
  if (typeof date !== "number") {
    return false;
  }
  return now >= date && now - date < FRESH_MS;
}

module.exports = {
  phoneDelivery,
  phoneSetup,
  pushIsFresh,
  pushIssueId,
};
