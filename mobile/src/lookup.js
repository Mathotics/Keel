const SEPARATOR = " \u2014 ";
const LIMIT = 10;
const LOOKUP_PROJECT = "Pick a project from the list.";
const LOOKUP_PERSON = "Pick a person from the list.";
const LOOKUP_ISSUE = "Pick an issue from the list.";

function projectLabel(project) {
  return `${project.key}${SEPARATOR}${project.name}`;
}

function issueLabel(issue) {
  return `${issue.key}${SEPARATOR}${issue.title}`;
}

function suggestProjects(projects, query) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle) {
    return [];
  }
  return (projects || [])
    .filter((project) => {
      const key = String(project.key || "").toLowerCase();
      const name = String(project.name || "").toLowerCase();
      return key.includes(needle) || name.includes(needle);
    })
    .sort((left, right) => String(left.key).localeCompare(String(right.key)))
    .slice(0, LIMIT)
    .map((project) => ({ id: project.id, label: projectLabel(project) }));
}

function suggestPeople(people, query) {
  const needle = String(query || "").trim().toLowerCase();
  const results = [];
  if (!needle || "unassigned".startsWith(needle)) {
    results.push({ id: null, label: "Unassigned" });
  }
  if (!needle) {
    return results;
  }
  const ranked = (people || []).slice().sort((left, right) =>
    String(left.display_name || "").localeCompare(String(right.display_name || "")),
  );
  for (const person of ranked) {
    const name = String(person.display_name || "");
    const username = String(person.username || "");
    if (name.toLowerCase() === "unassigned") {
      continue;
    }
    if (name.toLowerCase().includes(needle) || username.toLowerCase().includes(needle)) {
      results.push({ id: person.id, label: name });
    }
    if (results.length >= LIMIT) {
      break;
    }
  }
  return results.slice(0, LIMIT);
}

function suggestIssues(issues, query) {
  const needle = String(query || "").trim().toLowerCase();
  if (!needle) {
    return [];
  }
  return (issues || [])
    .filter((issue) => {
      const key = String(issue.key || "").toLowerCase();
      const title = String(issue.title || "").toLowerCase();
      return key.includes(needle) || title.includes(needle);
    })
    .sort((left, right) => String(left.key).localeCompare(String(right.key)))
    .slice(0, LIMIT)
    .map((issue) => ({
      id: issue.id,
      label: issueLabel(issue),
      type: issue.type,
      projectId: issue.projectId,
    }));
}

function lookupDirty(committed, text) {
  const shown = String(text || "");
  return shown.trim() !== "" && shown !== committed;
}

module.exports = {
  LOOKUP_ISSUE,
  LOOKUP_PERSON,
  LOOKUP_PROJECT,
  issueLabel,
  lookupDirty,
  projectLabel,
  suggestIssues,
  suggestPeople,
  suggestProjects,
};
