// Menu dismiss is a leftward swipe anywhere on the open menu.
// Page back is a rightward swipe that starts at the left edge, so a
// sideways board scroll in the middle of the screen is left alone.

const MENU_CAPTURE = -24;
const MENU_RELEASE = -48;
const MENU_VELOCITY = -0.4;
const BACK_EDGE = 32;
const BACK_CAPTURE = 12;
const BACK_RELEASE = 48;
const BACK_VELOCITY = 0.4;

function claimsMenuDismiss(gesture) {
  return gesture.dx <= MENU_CAPTURE && Math.abs(gesture.dx) > Math.abs(gesture.dy);
}

function releasesMenuDismiss(gesture) {
  return gesture.dx <= MENU_RELEASE || gesture.vx <= MENU_VELOCITY;
}

function claimsPageBack(gesture) {
  if (!gesture || typeof gesture.x0 !== "number" || typeof gesture.dx !== "number") {
    return false;
  }
  const dy = typeof gesture.dy === "number" ? gesture.dy : 0;
  return gesture.x0 <= BACK_EDGE && gesture.dx >= BACK_CAPTURE && Math.abs(gesture.dx) > Math.abs(dy);
}

function releasesPageBack(gesture) {
  if (!gesture || typeof gesture.dx !== "number") {
    return false;
  }
  const vx = typeof gesture.vx === "number" ? gesture.vx : 0;
  return gesture.dx >= BACK_RELEASE || vx >= BACK_VELOCITY;
}

const ROOT_PHASES = ["booting", "locked", "signedOut"];
const HISTORY_LIMIT = 40;

function notePhase(history, previous, phase, restoring) {
  const stack = Array.isArray(history) ? history : [];
  if (phase === previous) {
    return { history: stack, previous, restoring: Boolean(restoring) };
  }
  if (ROOT_PHASES.includes(phase)) {
    return { history: [], previous: phase, restoring: false };
  }
  if (restoring) {
    return { history: stack, previous: phase, restoring: false };
  }
  if (stack.length && stack[stack.length - 1] === phase) {
    return { history: stack.slice(0, -1), previous: phase, restoring: false };
  }
  if (ROOT_PHASES.includes(previous)) {
    return { history: stack, previous: phase, restoring: false };
  }
  const next = stack.concat(previous);
  return {
    history: next.length > HISTORY_LIMIT ? next.slice(-HISTORY_LIMIT) : next,
    previous: phase,
    restoring: false,
  };
}

module.exports = {
  BACK_EDGE,
  claimsMenuDismiss,
  claimsPageBack,
  notePhase,
  releasesMenuDismiss,
  releasesPageBack,
};
