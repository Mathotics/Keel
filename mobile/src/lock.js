const ALWAYS = "always";
const ON_RESUME = "on-resume";
const ON_LAUNCH = "on-launch";

function shouldUnlock({ signedIn, setting, hasDeviceLock, event }) {
  if (!signedIn || !hasDeviceLock || setting === ALWAYS) {
    return false;
  }
  if (event === "launch") {
    return setting === ON_LAUNCH || setting === ON_RESUME;
  }
  if (event === "resume") {
    return setting === ON_RESUME;
  }
  return false;
}

module.exports = {
  ALWAYS,
  ON_LAUNCH,
  ON_RESUME,
  shouldUnlock,
};
