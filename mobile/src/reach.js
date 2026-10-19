const listeners = new Set();
let online = false;
let known = false;
let forced = false;

function reachability() {
  return online;
}

function reachabilityKnown() {
  return known;
}

function forcedOffline() {
  return forced;
}

function setForcedOffline(next) {
  forced = Boolean(next);
}

function connectionMode(networkOnline, locked) {
  if (locked) {
    return "locked";
  }
  return networkOnline ? "online" : "offline";
}

function shouldStayOffline({ known: isKnown, online: isOnline, forced: isForced }) {
  return Boolean(isForced) || (Boolean(isKnown) && !isOnline);
}

function setReachable(next) {
  const value = Boolean(next);
  known = true;
  if (value === online) {
    return;
  }
  online = value;
  listeners.forEach((listener) => listener(online));
}

function subscribeReachability(listener) {
  listeners.add(listener);
  listener(online);
  return () => listeners.delete(listener);
}

module.exports = {
  connectionMode,
  forcedOffline,
  reachability,
  reachabilityKnown,
  setForcedOffline,
  setReachable,
  shouldStayOffline,
  subscribeReachability,
};
