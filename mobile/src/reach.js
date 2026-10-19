const listeners = new Set();
let online = false;

function reachability() {
  return online;
}

function setReachable(next) {
  const value = Boolean(next);
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
  setReachable,
  subscribeReachability,
};
