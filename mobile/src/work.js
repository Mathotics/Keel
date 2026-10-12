const STATUS_LABELS = {
  todo: "To Do",
  in_progress: "In Progress",
  in_review: "In Review",
  blocked: "Blocked",
  done: "Done",
  cancelled: "Cancelled",
};

const NO_ACTIVE_SPRINT = "No active sprint.";
const NO_ISSUES = "No issues in this sprint.";
const NO_PROJECTS = "No projects yet.";

function statusLabel(status) {
  return STATUS_LABELS[status] || status;
}

function activeSprint(sprints) {
  const found = (sprints || []).find((sprint) => sprint && sprint.state === "active");
  return found || null;
}

function workSection(project, sprints, detail) {
  const sprint = activeSprint(sprints);
  const issues =
    sprint && detail && detail.id === sprint.id && detail.state === "active"
      ? (detail.issues || []).map((issue) => ({
          id: issue.id,
          key: issue.key,
          title: issue.title,
          status: issue.status,
          statusLabel: statusLabel(issue.status),
        }))
      : [];
  return {
    projectId: project.id,
    projectKey: project.key,
    projectName: project.name,
    sprintName: sprint ? sprint.name : null,
    issues,
  };
}

module.exports = {
  NO_ACTIVE_SPRINT,
  NO_ISSUES,
  NO_PROJECTS,
  activeSprint,
  statusLabel,
  workSection,
};
