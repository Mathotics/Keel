const { statusLabel } = require("./work");

const TYPE_LABELS = {
  epic: "Epic",
  story: "Story",
  subtask: "Subtask",
};

const PRIORITY_LABELS = {
  p1: "P1 — Blocker",
  p2: "P2 — Critical",
  p3: "P3 — Major",
  p4: "P4 — Minor",
  p5: "P5 — Trivial",
};

const MINUTES_PER_HOUR = 60;
const MINUTES_PER_DAY = 8 * MINUTES_PER_HOUR;

function typeLabel(type) {
  return TYPE_LABELS[type] || type;
}

function priorityLabel(priority) {
  return PRIORITY_LABELS[priority] || priority;
}

function formatMinutes(minutes) {
  if (minutes === null || minutes === undefined) {
    return "None";
  }
  const days = Math.floor(minutes / MINUTES_PER_DAY);
  const rest = minutes % MINUTES_PER_DAY;
  const hours = Math.floor(rest / MINUTES_PER_HOUR);
  const remaining = rest % MINUTES_PER_HOUR;
  const parts = [];
  if (days) {
    parts.push(`${days}d`);
  }
  if (hours) {
    parts.push(`${hours}h`);
  }
  if (remaining || parts.length === 0) {
    parts.push(`${remaining}m`);
  }
  return parts.join(" ");
}

function formatWhen(value) {
  if (!value) {
    return "None";
  }
  const text = String(value);
  const utc = /Z$|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`;
  const date = new Date(utc);
  if (Number.isNaN(date.getTime())) {
    return text;
  }
  const pad = (part) => String(part).padStart(2, "0");
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())} UTC`;
}

function personName(users, id, missing) {
  if (id === null || id === undefined) {
    return missing;
  }
  const found = (users || []).find((user) => user.id === id);
  return found ? found.display_name : missing;
}

function parseInlines(text) {
  const pattern =
    /(`[^`]+`|\*\*[^*]+\*\*|__[^_]+__|\*[^*]+\*|_[^_]+_|\[[^\]]+\]\([^)]+\))/g;
  const runs = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) {
      runs.push({ text: text.slice(last, match.index) });
    }
    const token = match[0];
    if (token.startsWith("`")) {
      runs.push({ text: token.slice(1, -1), code: true });
    } else if (token.startsWith("**") || token.startsWith("__")) {
      runs.push({ text: token.slice(2, -2), bold: true });
    } else if (token.startsWith("*") || token.startsWith("_")) {
      runs.push({ text: token.slice(1, -1), italic: true });
    } else {
      runs.push({ text: token.slice(1, token.indexOf("]")) });
    }
    last = match.index + token.length;
  }
  if (last < text.length) {
    runs.push({ text: text.slice(last) });
  }
  return runs.filter((run) => run.text);
}

function parseMarkdown(source) {
  const text = (source || "").replaceAll("\r\n", "\n").trim();
  if (!text) {
    return [];
  }
  const blocks = [];
  const lines = text.split("\n");
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const body = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        body.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push({ type: "code", text: body.join("\n") });
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[1].length,
        inlines: parseInlines(heading[2]),
      });
      index += 1;
      continue;
    }
    if (/^(\d+\.|[-*])\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^(\d+\.|[-*])\s+/.test(lines[index])) {
        items.push(parseInlines(lines[index].replace(/^(\d+\.|[-*])\s+/, "")));
        index += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }
    const paragraph = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].startsWith("```") &&
      !/^(#{1,6})\s+/.test(lines[index]) &&
      !/^(\d+\.|[-*])\s+/.test(lines[index])
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", inlines: parseInlines(paragraph.join(" ")) });
  }
  return blocks;
}

function linkedIssue(issue, link) {
  const otherProject = !String(issue.key || "").startsWith(`${link.project_key}-`);
  return {
    id: link.id,
    key: link.key,
    title: link.title,
    projectKey: otherProject ? link.project_key : null,
  };
}

function issuePage({
  issue,
  users,
  parent,
  children,
  dependencies,
  history,
  historyAvailable,
  sprint,
}) {
  const groups = dependencies || { blocks: [], blocked_by: [], relates_to: [] };
  return {
    id: issue.id,
    key: issue.key,
    title: issue.title,
    typeLabel: typeLabel(issue.type),
    statusLabel: statusLabel(issue.status),
    priorityLabel: priorityLabel(issue.priority),
    assignee: personName(users, issue.assignee_id, "Unassigned"),
    reporter: personName(users, issue.reporter_id, "None"),
    labels: issue.labels && issue.labels.length ? issue.labels.join(", ") : "None",
    start: formatWhen(issue.start_at),
    due: formatWhen(issue.due_at),
    created: formatWhen(issue.created_at),
    updated: formatWhen(issue.updated_at),
    estimate: formatMinutes(issue.estimate_minutes),
    remaining: formatMinutes(issue.remaining_minutes),
    rollup:
      issue.rollup && issue.rollup.descendants
        ? {
            estimate: formatMinutes(issue.rollup.estimate_minutes),
            remaining: formatMinutes(issue.rollup.remaining_minutes),
            progress: `${issue.rollup.descendants_done} of ${issue.rollup.descendants} done`,
            cancelled: issue.rollup.descendants_cancelled
              ? `${issue.rollup.descendants_cancelled} cancelled`
              : null,
          }
        : null,
    description: parseMarkdown(issue.description),
    sprintName: sprint ? sprint.name : null,
    parent: parent ? { id: parent.id, key: parent.key, title: parent.title } : null,
    children: (children || []).map((child) => ({
      id: child.id,
      key: child.key,
      title: child.title,
      statusLabel: statusLabel(child.status),
    })),
    blocks: (groups.blocks || []).map((link) => linkedIssue(issue, link)),
    blockedBy: (groups.blocked_by || []).map((link) => linkedIssue(issue, link)),
    relatesTo: (groups.relates_to || []).map((link) => linkedIssue(issue, link)),
    historyAvailable: historyAvailable !== false,
    history: (history || []).map(
      (event) =>
        `${formatWhen(event.created_at)}, ${event.actor_name} — ${event.field} ${event.from_value} → ${event.to_value}`,
    ),
  };
}

module.exports = {
  formatMinutes,
  formatWhen,
  issuePage,
  parseMarkdown,
};
