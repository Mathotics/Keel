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

const SYMBOLS = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  CAD: "$",
  AUD: "$",
  NZD: "$",
  JPY: "¥",
  CNY: "¥",
  INR: "₹",
  MXN: "$",
  BRL: "R$",
  CHF: "Fr",
  SEK: "kr",
  NOK: "kr",
  DKK: "kr",
  SGD: "$",
  HKD: "$",
  KRW: "₩",
  ZAR: "R",
};

const ZERO_DECIMAL = new Set([
  "BIF",
  "CLP",
  "DJF",
  "GNF",
  "ISK",
  "JPY",
  "KMF",
  "KRW",
  "PYG",
  "RWF",
  "UGX",
  "UYI",
  "VND",
  "VUV",
  "XAF",
  "XOF",
  "XPF",
]);

const KNOWN_SYMBOLS = ["R$", "Fr", "kr", "₩", "₹", "¥", "€", "£", "$", "R"];

function projectCurrency(project) {
  const code = project && project.currency ? String(project.currency).trim().toUpperCase() : "USD";
  return /^[A-Z]{3}$/.test(code) ? code : "USD";
}

function costExample(code) {
  const symbol = SYMBOLS[code] || "";
  return `Cost must look like 12, 12.50, or ${symbol}1,234.56 ${code}.`;
}

function groupThousands(value) {
  const parts = [];
  let rest = String(value);
  while (rest.length > 3) {
    parts.unshift(rest.slice(-3));
    rest = rest.slice(0, -3);
  }
  parts.unshift(rest);
  return parts.join(",");
}

function formatMoney(cents, currency, style) {
  if (cents === null || cents === undefined || Number.isNaN(Number(cents))) {
    return "None";
  }
  const code = projectCurrency({ currency: currency || "USD" });
  const places = style === "display" && ZERO_DECIMAL.has(code) ? 0 : 2;
  const negative = cents < 0;
  const amount = Math.abs(Math.trunc(Number(cents)));
  const dollars = Math.floor(amount / 100);
  const remainder = amount % 100;
  const grouped = groupThousands(dollars);
  const digits = places === 0 ? grouped : `${grouped}.${String(remainder).padStart(2, "0")}`;
  const symbol = SYMBOLS[code] || "";
  const body = `${symbol}${digits} ${code}`;
  return negative ? `-${body}` : body;
}

function groupedDollars(text) {
  if (!text.includes(",")) {
    return /^\d+$/.test(text);
  }
  const groups = text.split(",");
  if (!/^\d{1,3}$/.test(groups[0])) {
    return false;
  }
  return groups.slice(1).every((group) => /^\d{3}$/.test(group));
}

function parseAmount(raw, currency) {
  const code = projectCurrency({ currency: currency || "USD" });
  const cleaned = String(raw || "").trim();
  if (!cleaned) {
    return { value: null };
  }
  if (cleaned.includes("-")) {
    return { error: costExample(code) };
  }
  let body = cleaned;
  const suffix = cleaned.slice(-3);
  if (/^[A-Za-z]{3}$/.test(suffix)) {
    if (suffix.toUpperCase() !== code) {
      return { error: costExample(code) };
    }
    body = cleaned.slice(0, -3).trim();
  }
  const symbol = SYMBOLS[code] || "";
  for (const known of KNOWN_SYMBOLS) {
    if (body.startsWith(known)) {
      if (known !== symbol) {
        return { error: costExample(code) };
      }
      body = body.slice(known.length).trim();
      break;
    }
  }
  const dot = body.indexOf(".");
  const dollarsText = dot === -1 ? body : body.slice(0, dot);
  const fractionText = dot === -1 ? "" : body.slice(dot + 1);
  if (
    !dollarsText
    || (dot !== -1 && body.indexOf(".", dot + 1) !== -1)
    || (dot !== -1 && !/^\d{1,2}$/.test(fractionText))
    || !groupedDollars(dollarsText)
  ) {
    return { error: costExample(code) };
  }
  const dollars = Number(dollarsText.replaceAll(",", ""));
  if (!Number.isSafeInteger(dollars)) {
    return { error: costExample(code) };
  }
  const fraction = fractionText.padEnd(2, "0");
  return { value: dollars * 100 + Number(fraction) };
}

function formatIndex(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "N/A";
  }
  let text = Number(value).toFixed(4).replace(/0+$/, "").replace(/\.$/, "");
  if (!text.includes(".")) {
    text += ".00";
  } else if (text.split(".")[1].length < 2) {
    text += "0";
  }
  return text;
}

function costIndex(numerator, denominator) {
  if (numerator == null || denominator == null || denominator === 0) {
    return null;
  }
  return Math.round((numerator / denominator) * 10000) / 10000;
}

function costMetrics(source) {
  if (!source) {
    return { bac: null, eac: null, spi: null, cpi: null };
  }
  if (Object.prototype.hasOwnProperty.call(source, "budget_at_completion_cents")) {
    return {
      bac: source.budget_at_completion_cents ?? null,
      eac: source.estimate_at_completion_cents ?? null,
      spi: source.schedule_performance_index ?? null,
      cpi: source.cost_performance_index ?? null,
    };
  }
  const planned = source.planned_value_cents ?? null;
  const earned = source.earned_value_cents ?? null;
  const actual = source.actual_cost_cents ?? null;
  return {
    bac: planned,
    eac: planned != null && earned != null && actual != null ? actual + planned - earned : null,
    spi: costIndex(earned, planned),
    cpi: costIndex(earned, actual),
  };
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
    dependencyId: link.dependency_id,
    key: link.key,
    title: link.title,
    projectKey: otherProject ? link.project_key : null,
  };
}

function issueKeyParts(raw) {
  const matched = /^([A-Za-z][A-Za-z0-9]{1,9})-(\d+)$/.exec(String(raw || "").trim());
  if (!matched) {
    return null;
  }
  return { key: matched[1].toUpperCase(), number: Number(matched[2]) };
}

function savedIssueId(library, rawKey) {
  const parts = issueKeyParts(rawKey);
  if (!parts) {
    return null;
  }
  const wanted = `${parts.key}-${parts.number}`;
  for (const project of Object.values((library && library.projects) || {})) {
    for (const record of Object.values((project && project.issues) || {})) {
      const issue = record.raw || {};
      if (String(issue.key || "").toUpperCase() === wanted && Number(issue.id) > 0) {
        return issue.id;
      }
    }
  }
  return null;
}

function linkEnds(issueId, otherId, relation) {
  if (relation === "blocks") {
    return { source_id: issueId, target_id: otherId, kind: "blocks" };
  }
  if (relation === "blocked_by") {
    return { source_id: otherId, target_id: issueId, kind: "blocks" };
  }
  if (relation === "relates_to") {
    return { source_id: issueId, target_id: otherId, kind: "relates_to" };
  }
  return null;
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
  comments,
  currency,
}) {
  const code = projectCurrency({ currency });
  const groups = dependencies || { blocks: [], blocked_by: [], relates_to: [] };
  return {
    id: issue.id,
    key: issue.key,
    projectId: issue.project_id,
    seriesId: issue.series_id || null,
    formerSeries: issue.former_series_title || "",
    descriptionText: issue.description || "",
    definitionOfDoneText: issue.definition_of_done || "",
    location: (issue.location || "").trim() || "None",
    type: issue.type,
    priority: issue.priority,
    parentId: issue.parent_id || null,
    assigneeId: issue.assignee_id || null,
    title: issue.title,
    typeLabel: typeLabel(issue.type),
    status: issue.status,
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
    plannedValue: formatMoney(issue.planned_value_cents ?? 0, code, "display"),
    earnedValue: formatMoney(issue.earned_value_cents ?? 0, code, "display"),
    actualCost: formatMoney(issue.actual_cost_cents ?? 0, code, "display"),
    budgetAtCompletion: formatMoney(costFigures(issue).bac ?? 0, code, "display"),
    estimateAtCompletion: formatMoney(costFigures(issue).eac ?? 0, code, "display"),
    schedulePerformanceIndex: formatIndex(costFigures(issue).spi),
    costPerformanceIndex: formatIndex(costFigures(issue).cpi),
    rollup:
      issue.rollup && issue.rollup.descendants
        ? {
            estimate: formatMinutes(issue.rollup.estimate_minutes),
            remaining: formatMinutes(issue.rollup.remaining_minutes),
            plannedValue: formatMoney(issue.rollup.planned_value_cents ?? 0, code, "display"),
            earnedValue: formatMoney(issue.rollup.earned_value_cents ?? 0, code, "display"),
            actualCost: formatMoney(issue.rollup.actual_cost_cents ?? 0, code, "display"),
            progress: `${issue.rollup.descendants_done} of ${issue.rollup.descendants} done`,
            cancelled: issue.rollup.descendants_cancelled
              ? `${issue.rollup.descendants_cancelled} cancelled`
              : null,
          }
        : null,
    description: parseMarkdown(issue.description),
    definitionOfDone: parseMarkdown(issue.definition_of_done),
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
    comments: (comments || []).map((comment) => commentView(comment, users)),
  };
}

function commentView(comment, users) {
  return {
    id: comment.id,
    author: comment.author || personName(users, comment.author_id, "Someone"),
    created: formatWhen(comment.created_at),
    body: comment.body,
    blocks: parseMarkdown(comment.body),
    pending: Boolean(comment.pending),
  };
}

function amountForEditing(value, currency) {
  const parsed = parseAmount(value, currency);
  if (parsed.error || parsed.value == null) {
    return String(value || "").trim();
  }
  const whole = Math.floor(parsed.value / 100);
  const fraction = String(parsed.value % 100).padStart(2, "0");
  return `${whole}.${fraction}`;
}

function amountForIdle(value, currency) {
  const cleaned = String(value || "").trim();
  if (!cleaned) {
    return "";
  }
  const parsed = parseAmount(cleaned, currency);
  if (parsed.error || parsed.value == null) {
    return cleaned;
  }
  return formatMoney(parsed.value, currency, "edit");
}

function costFigures(issue) {
  if (issue.rollup && issue.rollup.descendants) {
    return costMetrics(issue.rollup);
  }
  return costMetrics(issue);
}

module.exports = {
  commentView,
  formatIndex,
  formatMinutes,
  formatMoney,
  amountForEditing,
  amountForIdle,
  formatWhen,
  parseAmount,
  projectCurrency,
  issueKeyParts,
  issuePage,
  linkEnds,
  parseMarkdown,
  priorityLabel,
  savedIssueId,
  typeLabel,
};
