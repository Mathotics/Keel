const FAILED = "Could not connect.";

function detailMessage(body, fallback) {
  const detail = body && body.detail;
  if (typeof detail === "string" && detail) {
    return detail;
  }
  if (detail && typeof detail.message === "string" && detail.message) {
    return detail.message;
  }
  return fallback;
}

async function readBody(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function request(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function login(origin, username, password, label) {
  let response;
  try {
    response = await request(`${origin}/api/v1/login`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ username, password, label }),
    });
  } catch {
    const error = new Error(FAILED);
    error.status = 0;
    throw error;
  }
  const body = await readBody(response);
  if (!response.ok) {
    const error = new Error(detailMessage(body, FAILED));
    error.status = response.status;
    throw error;
  }
  return body;
}

async function renameLabel(origin, token, tokenId, label) {
  return send(origin, token, "PATCH", `/api/v1/profile/tokens/${tokenId}`, {
    label,
  });
}

async function revokeToken(origin, token, tokenId) {
  return send(origin, token, "DELETE", `/api/v1/profile/tokens/${tokenId}`);
}

async function send(origin, token, method, path, payload) {
  let response;
  try {
    response = await request(`${origin}${path}`, {
      method,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(payload ? { "Content-Type": "application/json" } : {}),
      },
      body: payload ? JSON.stringify(payload) : undefined,
    });
  } catch {
    const error = new Error(FAILED);
    error.status = 0;
    throw error;
  }
  if (response.status === 401) {
    const error = new Error("Sign in.");
    error.status = 401;
    throw error;
  }
  if (!response.ok && response.status !== 204) {
    const error = new Error(FAILED);
    error.status = response.status;
    throw error;
  }
  return response.status;
}

module.exports = {
  login,
  renameLabel,
  revokeToken,
};
