const listeners = new Set();
let online = false;
let known = false;

function reachability() {
  return online;
}

function reachabilityKnown() {
  return known;
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
  reachability,
  reachabilityKnown,
  setReachable,
  subscribeReachability,
};
