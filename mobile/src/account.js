const NEEDS_CONNECTION = "Account needs a connection.";

function prepareProfile({ displayName, username }) {
  const name = cleanName(displayName);
  if (name.error) {
    return name;
  }
  const login = cleanUsername(username);
  if (login.error) {
    return login;
  }
  return { body: { display_name: name.value, username: login.value } };
}

function preparePassword({ current, next, confirm, username }) {
  if (!current) {
    return { error: "Enter your current password." };
  }
  const checked = checkNewPassword(next, confirm, username);
  if (checked.error) {
    return checked;
  }
  return {
    body: {
      current_password: current,
      new_password: next,
      confirm_password: confirm,
    },
  };
}

function preparePerson({ displayName, username, password, confirm }) {
  const name = cleanName(displayName);
  if (name.error) {
    return name;
  }
  const login = String(username || "").trim();
  if (login) {
    const checkedLogin = cleanUsername(login);
    if (checkedLogin.error) {
      return checkedLogin;
    }
  }
  const checked = checkNewPassword(password, confirm, login || name.value, "The passwords do not match.");
  if (checked.error) {
    return checked;
  }
  const body = { display_name: name.value, password };
  if (login) {
    body.username = login;
  }
  return { body };
}

function prepareRename(displayName) {
  return cleanName(displayName);
}

function cleanName(displayName) {
  const name = String(displayName || "").trim();
  if (!name) {
    return { error: "A user needs a display name." };
  }
  if (name.length > 100) {
    return { error: "A display name may be at most 100 characters." };
  }
  return { value: name };
}

function cleanUsername(username) {
  const login = String(username || "").trim();
  if (!login) {
    return { error: "A user needs a username." };
  }
  if (login.length > 100) {
    return { error: "A username may be at most 100 characters." };
  }
  return { value: login };
}

function checkNewPassword(password, confirm, username, mismatch) {
  if (password !== confirm) {
    return { error: mismatch || "The new passwords do not match." };
  }
  if (String(password || "").length < 12) {
    return { error: "A password must be at least 12 characters." };
  }
  if (String(password || "").length > 128) {
    return { error: "A password may be at most 128 characters." };
  }
  if (String(password).toLowerCase() === String(username || "").trim().toLowerCase()) {
    return { error: "A password must not match the username." };
  }
  return { ok: true };
}

function isThisPhone(token, tokenId) {
  return String(token && token.id) === String(tokenId);
}

function deviceWhen(value) {
  if (!value) {
    return "Not used yet";
  }
  return String(value).replace("T", " ").slice(0, 16);
}

module.exports = {
  NEEDS_CONNECTION,
  deviceWhen,
  isThisPhone,
  preparePassword,
  preparePerson,
  prepareProfile,
  prepareRename,
};
