const { activeSprint, workSection } = require("./work");
const { issuePage } = require("./issue");

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

async function read(origin, token, path) {
  let response;
  try {
    response = await request(`${origin}${path}`, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
      },
    });
  } catch {
    const error = new Error(FAILED);
    error.status = 0;
    throw error;
  }
  const body = await readBody(response);
  if (response.status === 401) {
    const error = new Error("Sign in.");
    error.status = 401;
    throw error;
  }
  if (!response.ok) {
    const error = new Error(detailMessage(body, FAILED));
    error.status = response.status;
    throw error;
  }
  return body;
}

async function loadWork(origin, token) {
  const projects = await read(origin, token, "/api/v1/projects");
  return Promise.all(
    projects.map(async (project) => {
      const sprints = await read(
        origin,
        token,
        `/api/v1/projects/${project.id}/sprints?state=active`,
      );
      const sprint = activeSprint(sprints);
      const detail = sprint
        ? await read(origin, token, `/api/v1/sprints/${sprint.id}`)
        : null;
      return workSection(project, sprints, detail);
    }),
  );
}

async function loadSnapshots(origin, token) {
  const projects = await read(origin, token, "/api/v1/projects");
  return Promise.all(
    projects.map(async (project) => {
      const sprints = await read(
        origin,
        token,
        `/api/v1/projects/${project.id}/sprints?state=active`,
      );
      const sprint = activeSprint(sprints);
      const detail = sprint
        ? await read(origin, token, `/api/v1/sprints/${sprint.id}`)
        : null;
      const active =
        sprint && detail && detail.id === sprint.id && detail.state === "active"
          ? sprint
          : null;
      return {
        project: { id: project.id, key: project.key, name: project.name },
        sprint: active ? { id: active.id, name: active.name, state: active.state } : null,
        issues: active ? detail.issues || [] : [],
      };
    }),
  );
}

async function loadCatalog(origin, token) {
  const [people, labels] = await Promise.all([
    read(origin, token, "/api/v1/users"),
    read(origin, token, "/api/v1/labels"),
  ]);
  return { people, labels };
}

async function loadProfile(origin, token) {
  return read(origin, token, "/api/v1/profile");
}

async function loadIssueDetail(origin, token, issueId) {
  const [issue, children, dependencies, users] = await Promise.all([
    read(origin, token, `/api/v1/issues/${issueId}`),
    read(origin, token, `/api/v1/issues/${issueId}/children`),
    read(origin, token, `/api/v1/issues/${issueId}/dependencies`),
    read(origin, token, "/api/v1/users"),
  ]);
  const parent = issue.parent_id
    ? await read(origin, token, `/api/v1/issues/${issue.parent_id}`)
    : null;
  let history = [];
  let historyAvailable = true;
  try {
    history = await read(origin, token, `/api/v1/issues/${issueId}/history`);
  } catch (error) {
    if (error.status !== 404) {
      throw error;
    }
    historyAvailable = false;
  }
  const sprint = issue.sprint_id
    ? await read(origin, token, `/api/v1/sprints/${issue.sprint_id}`)
    : null;
  return {
    issue,
    page: issuePage({
      issue,
      users,
      parent,
      children,
      dependencies,
      history,
      historyAvailable,
      sprint,
    }),
  };
}

async function loadIssue(origin, token, issueId) {
  const detail = await loadIssueDetail(origin, token, issueId);
  return detail.page;
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
  const body = await readBody(response);
  if (response.status === 401) {
    const error = new Error("Sign in.");
    error.status = 401;
    throw error;
  }
  if (!response.ok && response.status !== 204) {
    const error = new Error(detailMessage(body, FAILED));
    error.status = response.status;
    throw error;
  }
  if (response.status === 204) {
    return null;
  }
  return body;
}

module.exports = {
  loadCatalog,
  loadIssue,
  loadIssueDetail,
  loadProfile,
  loadSnapshots,
  loadWork,
  login,
  read,
  renameLabel,
  revokeToken,
  send,
};
