const NEEDS_CONNECTION = "Repeating schedules need a connection.";
const NONE = "No repeating series.";
const DELETE_TITLE = "Delete this schedule?";
const DELETE_BODY = "Existing issues remain. This cannot be undone.";
const DELETED = "Schedule deleted. Existing issues remain.";

const STATE_LABELS = { active: "Active", paused: "Paused" };
const TYPE_LABELS = { epic: "Epic", story: "Story", subtask: "Subtask" };
const PRIORITIES = [
  ["p1", "P1 — Blocker"],
  ["p2", "P2 — Critical"],
  ["p3", "P3 — Major"],
  ["p4", "P4 — Minor"],
  ["p5", "P5 — Trivial"],
];
const SPAWNS = [
  ["calendar", "On the calendar"],
  ["after_closed", "After the previous copy is closed"],
];
const BASES = [
  ["due_on", "Due date"],
  ["start_on", "Start date"],
  ["created_on", "Creation date"],
];
const FREQS = [
  ["daily", "Daily"],
  ["weekly", "Weekly"],
  ["monthly", "Monthly"],
  ["yearly", "Yearly"],
];
const SCOPES = [
  ["this", "This occurrence"],
  ["future", "This and all future"],
  ["series", "Entire series"],
];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function blankRecipe() {
  return {
    title: "",
    description: "",
    type: "story",
    priority: "p4",
    labels: "",
    spawnMode: "calendar",
    sprintBasis: "due_on",
    lookAhead: "1",
    startOffset: "",
    startTime: "",
    dueOffset: "",
    dueTime: "",
    freq: "weekly",
    interval: "1",
    startsOn: "",
    weekdays: [],
    monthDay: "",
    nthWeek: "",
    month: "",
    endMode: "never",
    endsOn: "",
    occurrenceCount: "",
    parentKey: "",
    assignee: "",
  };
}

function clockText(minute) {
  if (minute === null || minute === undefined || minute === "") {
    return "";
  }
  const hours = Math.floor(Number(minute) / 60);
  const minutes = Number(minute) % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

function recipeFromSeries(series, extras = {}) {
  const weekdays = String(series.weekdays || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map(Number);
  let endMode = "never";
  if (series.ends_on) {
    endMode = "on";
  } else if (series.occurrence_count) {
    endMode = "count";
  }
  return {
    ...blankRecipe(),
    title: series.title || "",
    description: series.description || "",
    type: series.type || "story",
    priority: series.priority || "p4",
    labels: (series.labels || []).join(", "),
    spawnMode: series.spawn_mode || "calendar",
    sprintBasis: series.sprint_basis || "due_on",
    lookAhead: String(series.look_ahead_n || 1),
    startOffset: series.start_offset_days == null ? "" : String(series.start_offset_days),
    startTime: clockText(series.start_minute_of_day),
    dueOffset: series.due_offset_days == null ? "" : String(series.due_offset_days),
    dueTime: clockText(series.due_minute_of_day),
    freq: series.freq || "weekly",
    interval: String(series.interval || 1),
    startsOn: series.starts_on || "",
    weekdays,
    monthDay: series.month_day ? String(series.month_day) : "",
    nthWeek: series.nth_week == null ? "" : String(series.nth_week),
    month: series.month ? String(series.month) : "",
    endMode,
    endsOn: series.ends_on || "",
    occurrenceCount: series.occurrence_count ? String(series.occurrence_count) : "",
    parentKey: extras.parentKey || "",
    assignee: extras.assignee || "",
  };
}

function dateField(raw, blankMessage) {
  const text = String(raw || "").trim();
  if (!text) {
    return blankMessage ? { error: blankMessage } : { value: null };
  }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    return { error: "A series date could not be read." };
  }
  return { value: text };
}

function positiveField(raw, message) {
  const text = String(raw || "").trim();
  if (!/^\d+$/.test(text) || Number(text) < 1) {
    return { error: message };
  }
  return { value: Number(text) };
}

function optionalOffset(raw) {
  const text = String(raw || "").trim();
  if (!text) {
    return { value: null };
  }
  if (!/^\d+$/.test(text)) {
    return { error: "Day offset could not be read." };
  }
  return { value: Number(text) };
}

function optionalClock(raw) {
  const text = String(raw || "").trim();
  if (!text) {
    return { value: null };
  }
  const matched = /^(\d{1,2}):(\d{2})$/.exec(text);
  if (!matched) {
    return { error: "Clock time could not be read." };
  }
  const value = Number(matched[1]) * 60 + Number(matched[2]);
  if (value < 0 || value >= 1440) {
    return { error: "Clock time must be on the clock." };
  }
  return { value };
}

function optionalInt(raw, message) {
  const text = String(raw || "").trim();
  if (!text) {
    return { value: null };
  }
  if (!/^-?\d+$/.test(text)) {
    return { error: message };
  }
  return { value: Number(text) };
}

function labelsOf(raw) {
  const seen = [];
  for (const part of String(raw || "").split(",")) {
    const name = part.trim().toLowerCase().replace(/\s+/g, "-");
    if (!name) {
      continue;
    }
    if (name.length > 40 || !/^[a-z0-9][a-z0-9_-]{0,39}$/.test(name)) {
      return { error: "Labels use letters, digits, hyphen, and underscore." };
    }
    if (!seen.includes(name)) {
      seen.push(name);
    }
  }
  return { value: seen };
}

function side(offset, clock) {
  if (offset.error) {
    return offset;
  }
  if (clock.error) {
    return clock;
  }
  if ((offset.value == null) !== (clock.value == null)) {
    return { error: "A start or due needs both a day offset and a time, or neither." };
  }
  return { offset: offset.value, clock: clock.value };
}

function prepareRecipe(draft, options = {}) {
  const requireTitle = options.requireTitle !== false;
  const title = String((draft && draft.title) || "").trim();
  if (requireTitle && !title) {
    return { error: "A series needs a title." };
  }
  const starts = dateField(draft.startsOn, "A series needs a start date.");
  if (starts.error) {
    return starts;
  }
  const interval = positiveField(draft.interval, "Repeat interval must be at least 1.");
  if (interval.error) {
    return interval;
  }
  const lookAhead = positiveField(draft.lookAhead, "Look-ahead must be at least 1.");
  if (lookAhead.error) {
    return lookAhead;
  }
  const start = side(optionalOffset(draft.startOffset), optionalClock(draft.startTime));
  if (start.error) {
    return start;
  }
  const due = side(optionalOffset(draft.dueOffset), optionalClock(draft.dueTime));
  if (due.error) {
    return due;
  }
  if (
    start.offset != null
    && start.clock != null
    && due.offset != null
    && due.clock != null
    && -start.offset * 1440 + start.clock > due.offset * 1440 + due.clock
  ) {
    return { error: "Start cannot be after due." };
  }
  const labels = labelsOf(draft.labels);
  if (labels.error) {
    return labels;
  }
  const monthDay = optionalInt(draft.monthDay, "Day of month could not be read.");
  if (monthDay.error) {
    return monthDay;
  }
  if (monthDay.value != null && (monthDay.value < 1 || monthDay.value > 31)) {
    return { error: "Day of month could not be read." };
  }
  const month = optionalInt(draft.month, "Month could not be read.");
  if (month.error) {
    return month;
  }
  if (month.value != null && (month.value < 1 || month.value > 12)) {
    return { error: "Month could not be read." };
  }
  const nthWeek = optionalInt(draft.nthWeek, "Nth weekday could not be read.");
  if (nthWeek.error) {
    return nthWeek;
  }
  const weekdays = (draft.weekdays || [])
    .map(Number)
    .filter((day) => day >= 0 && day <= 6)
    .sort((left, right) => left - right);
  let endsOn = null;
  let occurrenceCount = null;
  if (draft.endMode === "on") {
    const end = dateField(draft.endsOn, "A series date could not be read.");
    if (end.error) {
      return end;
    }
    endsOn = end.value;
  } else if (draft.endMode === "count") {
    const count = positiveField(draft.occurrenceCount, "Occurrence count must be at least 1.");
    if (count.error) {
      return count;
    }
    occurrenceCount = count.value;
  }
  const body = {
    description: String(draft.description || ""),
    priority: draft.priority || "p4",
    spawn_mode: draft.spawnMode || "calendar",
    sprint_basis: draft.sprintBasis || "due_on",
    freq: draft.freq || "weekly",
    interval: interval.value,
    weekdays,
    month_day: monthDay.value,
    nth_week: nthWeek.value,
    month: month.value,
    starts_on: starts.value,
    ends_on: endsOn,
    occurrence_count: occurrenceCount,
    look_ahead_n: lookAhead.value,
    start_offset_days: start.offset,
    start_minute_of_day: start.clock,
    due_offset_days: due.offset,
    due_minute_of_day: due.clock,
    labels: labels.value,
  };
  if (requireTitle) {
    body.title = title;
    body.type = draft.type || "story";
  }
  return { body };
}

function seriesView({ series, online }) {
  if (!online) {
    return { banner: NEEDS_CONNECTION, empty: "", rows: [] };
  }
  const rows = (series || []).map((item) => ({
    id: item.id,
    title: item.title,
    summary: item.cadence_summary || "",
    state: item.state,
    stateLabel: STATE_LABELS[item.state] || item.state,
    typeLabel: TYPE_LABELS[item.type] || item.type,
  }));
  return {
    banner: "",
    empty: rows.length ? "" : NONE,
    rows,
  };
}

module.exports = {
  BASES,
  DELETE_BODY,
  DELETE_TITLE,
  DELETED,
  FREQS,
  MONTHS,
  NEEDS_CONNECTION,
  NONE,
  PRIORITIES,
  SCOPES,
  SPAWNS,
  WEEKDAYS,
  blankRecipe,
  prepareRecipe,
  recipeFromSeries,
  seriesView,
};
