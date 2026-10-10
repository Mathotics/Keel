const EMPTY = "Enter the server address.";
const INVALID = "Enter a full address, including http:// or https://.";

function parseOrigin(input) {
  const trimmed = input.trim().replace(/\/+$/, "");
  if (!trimmed) {
    return { ok: false, message: EMPTY };
  }

  let url;
  try {
    url = new URL(trimmed);
  } catch {
    return { ok: false, message: INVALID };
  }

  const hasPath = url.pathname !== "" && url.pathname !== "/";
  if (
    (url.protocol !== "http:" && url.protocol !== "https:") ||
    !url.hostname ||
    url.username ||
    url.password ||
    hasPath ||
    url.search ||
    url.hash
  ) {
    return { ok: false, message: INVALID };
  }

  return { ok: true, origin: url.origin };
}

function healthUrl(origin) {
  return `${origin}/health`;
}

function isConnected(body) {
  return (
    typeof body === "object" &&
    body !== null &&
    "status" in body &&
    body.status === "ok"
  );
}

module.exports = {
  EMPTY,
  INVALID,
  parseOrigin,
  healthUrl,
  isConnected,
};
