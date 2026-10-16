const NEEDS_CONNECTION = "Anything outside the saved active sprint needs a connection.";
const ENTER_QUERY = "Enter a query.";
const NONE = "None.";
const MORE = {
  issues: "More issues match. Narrow the query.",
  projects: "More projects match. Narrow the query.",
  sprints: "More sprints match. Narrow the query.",
  users: "More users match. Narrow the query.",
};
const SNIPPET_RADIUS = 40;

function contains(haystack, needle) {
  return String(haystack || "").toLowerCase().includes(String(needle || "").toLowerCase());
}

function snippet(text, needle) {
  const source = String(text || "");
  const index = source.toLowerCase().indexOf(String(needle || "").toLowerCase());
  if (!source || index < 0) {
    return "";
  }
  const start = Math.max(0, index - SNIPPET_RADIUS);
  const end = Math.min(source.length, index + needle.length + SNIPPET_RADIUS);
  let excerpt = source.slice(start, end).trim();
  if (start > 0) {
    excerpt = `…${excerpt}`;
  }
  if (end < source.length) {
    excerpt = `${excerpt}…`;
  }
  return excerpt;
}

function enabledProjects(library) {
  return Object.values((library && library.projects) || {})
    .filter((project) => project && project.enabled)
    .sort((left, right) => (left.key || "").localeCompare(right.key || ""));
}

function issueNumber(issue) {
  if (Number.isInteger(issue.number)) {
    return issue.number;
  }
  const matched = /-(\d+)$/.exec(issue.key || "");
  return matched ? Number(matched[1]) : 0;
}

function savedIssues(library) {
  const rows = [];
  for (const project of enabledProjects(library)) {
    const sprintId = project.sprint && project.sprint.state === "active" ? project.sprint.id : null;
    if (!sprintId) {
      continue;
    }
    for (const issue of Object.values(project.issues || {})) {
      const raw = issue.raw || {};
      if (raw.sprint_id !== sprintId) {
        continue;
      }
      const comments = ((issue.page && issue.page.comments) || []).map((comment) => comment.body || "");
      rows.push({ raw, project, comments });
    }
  }
  return rows.sort((left, right) => {
    const project = (left.project.key || "").localeCompare(right.project.key || "");
    return project || issueNumber(left.raw) - issueNumber(right.raw);
  });
}

function issueSnippet(item, needle) {
  const raw = item.raw;
  if (contains(raw.key, needle) || contains(raw.title, needle)) {
    return "";
  }
  const described = snippet(raw.description, needle);
  if (described) {
    return described;
  }
  for (const body of item.comments) {
    const found = snippet(body, needle);
    if (found) {
      return found;
    }
  }
  return "";
}

function localFind(library, needle) {
  const saved = savedIssues(library);
  const exact = saved.find((item) => item.raw.key && item.raw.key.toLowerCase() === needle.toLowerCase());
  if (exact) {
    return {
      jump: {
        target: "issue",
        issueId: exact.raw.id,
        projectId: exact.project.id,
        key: exact.raw.key,
      },
    };
  }
  const issues = saved
    .filter((item) => {
      const raw = item.raw;
      return (
        contains(raw.key, needle) ||
        contains(raw.title, needle) ||
        contains(raw.description, needle) ||
        item.comments.some((body) => contains(body, needle))
      );
    })
    .map((item) => ({
      id: item.raw.id,
      projectId: item.project.id,
      target: "issue",
      title: item.raw.key || "New",
      detail: item.raw.title || "",
      meta: item.project.key || "",
      snippet: issueSnippet(item, needle),
    }));
  return {
    jump: null,
    query: needle,
    banner: NEEDS_CONNECTION,
    empty: issues.length ? "" : "",
    sections: [
      { key: "issues", label: "Issues", rows: issues, empty: issues.length ? "" : NONE, more: "" },
      { key: "projects", label: "Projects", rows: [], empty: "", more: "", needsConnection: true },
      { key: "sprints", label: "Sprints", rows: [], empty: "", more: "", needsConnection: true },
      { key: "users", label: "Users", rows: [], empty: "", more: "", needsConnection: true },
    ],
  };
}

function rowFromIssue(hit) {
  return {
    id: hit.id,
    projectId: null,
    target: "issue",
    title: hit.key,
    detail: hit.title,
    meta: hit.project_key,
    snippet: hit.snippet || "",
  };
}

function rowFromProject(hit) {
  return {
    id: hit.id,
    projectId: hit.id,
    target: "project",
    title: hit.key,
    detail: hit.name,
    meta: "",
    snippet: hit.snippet || "",
  };
}

function rowFromSprint(hit) {
  return {
    id: hit.id,
    projectId: hit.project_id,
    target: "sprint",
    title: hit.name,
    detail: "",
    meta: hit.project_key,
    snippet: hit.snippet || "",
  };
}

function rowFromUser(hit) {
  return {
    id: null,
    projectId: null,
    target: "user",
    title: hit.display_name,
    detail: "",
    meta: "",
    snippet: "",
  };
}

function section(key, label, rows, more) {
  return {
    key,
    label,
    rows,
    empty: rows.length ? "" : NONE,
    more: more ? MORE[key] : "",
    needsConnection: false,
  };
}

function findView({ library, query, payload }) {
  const needle = String(query || "").trim();
  if (!needle) {
    return { jump: null, query: "", prompt: ENTER_QUERY, banner: "", sections: [] };
  }
  if (!payload) {
    return { prompt: "", ...localFind(library, needle) };
  }
  if (payload.kind === "jump") {
    if (payload.target === "user") {
      return {
        jump: null,
        query: needle,
        prompt: "",
        banner: "",
        sections: [
          section("users", "Users", [rowFromUser(payload)], false),
        ],
      };
    }
    return {
      jump: {
        target: payload.target,
        issueId: payload.issue_id,
        projectId: payload.project_id,
        sprintId: payload.sprint_id,
        key: payload.key,
      },
      query: needle,
      prompt: "",
      banner: "",
      sections: [],
    };
  }
  return {
    jump: null,
    query: payload.query || needle,
    prompt: "",
    banner: "",
    sections: [
      section("issues", "Issues", (payload.issues || []).map(rowFromIssue), payload.issues_more),
      section("projects", "Projects", (payload.projects || []).map(rowFromProject), payload.projects_more),
      section("sprints", "Sprints", (payload.sprints || []).map(rowFromSprint), payload.sprints_more),
      section("users", "Users", (payload.users || []).map(rowFromUser), payload.users_more),
    ],
  };
}

module.exports = {
  ENTER_QUERY,
  MORE,
  NEEDS_CONNECTION,
  NONE,
  findView,
};
