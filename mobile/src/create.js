const PARENT = {
  epic: null,
  story: "epic",
  subtask: "story",
};

const EFFORT = "Effort must look like 2h, 90m, 1h 30m, or 1d.";
const MINUTES_PER_HOUR = 60;
const MINUTES_PER_DAY = 8 * MINUTES_PER_HOUR;

function parseDuration(raw) {
  const cleaned = String(raw || "").trim().replace(/\s+/g, " ");
  if (!cleaned) {
    return { value: null };
  }
  const seen = new Set();
  let total = 0;
  for (const part of cleaned.split(" ")) {
    const matched = /^(\d+)([dhm])$/i.exec(part);
    if (!matched) {
      return { error: EFFORT };
    }
    const unit = matched[2].toLowerCase();
    if (seen.has(unit)) {
      return { error: EFFORT };
    }
    seen.add(unit);
    const amount = Number(matched[1]);
    if (unit === "d") {
      total += amount * MINUTES_PER_DAY;
    } else if (unit === "h") {
      total += amount * MINUTES_PER_HOUR;
    } else {
      total += amount;
    }
  }
  return { value: total };
}

function parseWhen(raw) {
  const trimmed = String(raw || "").trim();
  if (!trimmed) {
    return { value: null };
  }
  const matched = /^(\d{4}-\d{2}-\d{2})(?:[ T](\d{2}):(\d{2}))?$/.exec(trimmed);
  if (!matched) {
    return { error: "Use a date like 2026-10-12 or 2026-10-12 09:00." };
  }
  const time = matched[2] ? `${matched[2]}:${matched[3]}:00` : "00:00:00";
  return { value: `${matched[1]}T${time}` };
}

function inputWhen(value) {
  if (!value) {
    return "";
  }
  const matched = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}):(\d{2})/.exec(String(value));
  if (!matched) {
    return "";
  }
  if (matched[2] === "00" && matched[3] === "00") {
    return matched[1];
  }
  return `${matched[1]} ${matched[2]}:${matched[3]}`;
}

function sameWhen(left, right) {
  return inputWhen(left) === inputWhen(right);
}

function sameLabels(left, right) {
  const first = left || [];
  const second = right || [];
  return first.length === second.length && first.every((label, index) => label === second[index]);
}

function article(word) {
  return "aeiou".includes(word[0]) ? `an ${word}` : `a ${word}`;
}

function invalidChildren(newType, childTypes) {
  for (const childType of childTypes || []) {
    if (PARENT[childType] !== newType) {
      return `Existing ${childType} children cannot sit under ${article(newType)}.`;
    }
  }
  return null;
}

function prepareCreate(input) {
  const title = String(input.title || "").trim();
  if (!title) {
    return { error: "Enter a title." };
  }
  const type = input.type || "story";
  const parent = input.parent || null;
  if (parent && parent.projectId !== input.projectId) {
    return { error: "A parent must belong to the same project." };
  }
  if (parent) {
    const expected = PARENT[type];
    if (!expected) {
      return { error: "An epic never has a parent." };
    }
    if (parent.type !== expected) {
      return {
        error: expected === "epic"
          ? "A story may only sit under an epic."
          : "A subtask may only sit under a story.",
      };
    }
  }
  const estimate = parseDuration(input.estimate);
  if (estimate.error) {
    return estimate;
  }
  const remaining = parseDuration(input.remaining);
  if (remaining.error) {
    return remaining;
  }
  const start = parseWhen(input.start);
  if (start.error) {
    return start;
  }
  const due = parseWhen(input.due);
  if (due.error) {
    return due;
  }
  if (start.value && due.value && due.value < start.value) {
    return { error: "Due must be after the start." };
  }
  const labels = String(input.labels || "")
    .split(",")
    .map((label) => label.trim())
    .filter(Boolean);
  return {
    error: null,
    draft: {
      projectId: input.projectId,
      title,
      type,
      description: String(input.description || ""),
      status: input.status || "todo",
      priority: input.priority || "p4",
      assignee_id: input.assigneeId || null,
      parent_id: parent ? parent.id : null,
      sprint_id: input.sprintId || null,
      estimate_minutes: estimate.value,
      remaining_minutes: remaining.value,
      start_at: start.value,
      due_at: due.value,
      labels,
    },
  };
}

function prepareUpdate(input) {
  const issue = input.issue;
  const prepared = prepareCreate({
    title: input.title,
    projectId: input.projectId,
    type: input.type,
    description: input.description,
    status: input.status,
    priority: input.priority,
    assigneeId: input.assigneeId,
    parent: input.parent,
    sprintId: input.sprintId,
    estimate: input.estimate,
    remaining: input.remaining,
    start: input.start,
    due: input.due,
    labels: input.labels,
  });
  if (prepared.error) {
    return prepared;
  }
  const draft = prepared.draft;
  if (input.parent && (input.parent.id === issue.id || (input.ancestorIds || []).includes(issue.id))) {
    return { error: "That parent would make the issue its own ancestor." };
  }
  const childError = invalidChildren(draft.type, input.childTypes);
  if (childError) {
    return { error: childError };
  }
  const nextSprint = draft.sprint_id ?? null;
  const currentSprint = issue.sprint_id ?? null;
  const activeSprint = input.activeSprintId ?? null;
  if (nextSprint !== currentSprint && nextSprint !== activeSprint && !input.online) {
    return { error: "Moving an issue off this sprint needs a connection." };
  }
  const changes = {};
  if (draft.title !== issue.title) {
    changes.title = draft.title;
  }
  if (draft.type !== issue.type) {
    changes.type = draft.type;
  }
  if ((draft.description || "") !== (issue.description || "")) {
    changes.description = draft.description;
  }
  if (draft.status !== issue.status) {
    changes.status = draft.status;
  }
  if (draft.priority !== issue.priority) {
    changes.priority = draft.priority;
  }
  if ((draft.assignee_id ?? null) !== (issue.assignee_id ?? null)) {
    changes.assignee_id = draft.assignee_id;
  }
  if ((draft.parent_id ?? null) !== (issue.parent_id ?? null)) {
    changes.parent_id = draft.parent_id;
  }
  if (nextSprint !== currentSprint) {
    changes.sprint_id = nextSprint;
  }
  if ((draft.estimate_minutes ?? null) !== (issue.estimate_minutes ?? null)) {
    changes.estimate_minutes = draft.estimate_minutes;
  }
  if ((draft.remaining_minutes ?? null) !== (issue.remaining_minutes ?? null)) {
    changes.remaining_minutes = draft.remaining_minutes;
  }
  if (!sameWhen(draft.start_at, issue.start_at)) {
    changes.start_at = draft.start_at;
  }
  if (!sameWhen(draft.due_at, issue.due_at)) {
    changes.due_at = draft.due_at;
  }
  if (!sameLabels(draft.labels, issue.labels)) {
    changes.labels = draft.labels;
  }
  return { error: null, changes };
}

module.exports = {
  inputWhen,
  prepareCreate,
  prepareUpdate,
};
