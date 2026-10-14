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

module.exports = {
  prepareCreate,
};
