const BULLET = "\u2022";

function maskPassword(password) {
  if (!password) {
    return "";
  }
  if (password.length === 1) {
    return password;
  }
  return BULLET.repeat(password.length - 1) + password.slice(-1);
}

function applyPasswordEdit(previousPassword, nextDisplay) {
  const previousDisplay = maskPassword(previousPassword);
  let prefix = 0;
  const maxPrefix = Math.min(previousDisplay.length, nextDisplay.length);
  while (prefix < maxPrefix && previousDisplay[prefix] === nextDisplay[prefix]) {
    prefix += 1;
  }
  let suffix = 0;
  while (
    suffix < previousDisplay.length - prefix &&
    suffix < nextDisplay.length - prefix &&
    previousDisplay[previousDisplay.length - 1 - suffix] ===
      nextDisplay[nextDisplay.length - 1 - suffix]
  ) {
    suffix += 1;
  }
  const inserted = nextDisplay
    .slice(prefix, nextDisplay.length - suffix)
    .replaceAll(BULLET, "");
  const passwordSuffix =
    suffix === 0 ? "" : previousPassword.slice(previousPassword.length - suffix);
  return previousPassword.slice(0, prefix) + inserted + passwordSuffix;
}

module.exports = {
  applyPasswordEdit,
  maskPassword,
};
