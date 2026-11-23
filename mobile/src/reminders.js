const DAY_MS = 86400000;
const UNIT_MS = { minute: 60000, hour: 3600000, day: DAY_MS };
const UNIT_WORDS = {
  minute: ["minute", "minutes"],
  hour: ["hour", "hours"],
  day: ["day", "days"],
};

function emptyBag() {
  return {
    defaultRule: null,
    seriesRules: [],
    issueRules: [],
    states: [],
    queue: [],
    delivered: {},
  };
}

function bag(store) {
  return (store && store.reminders) || emptyBag();
}

function parseWall(value) {
  if (!value) {
    return null;
  }
  const text = String(value);
  if (text.length < 16) {
    return null;
  }
  const year = Number(text.slice(0, 4));
  const month = Number(text.slice(5, 7));
  const day = Number(text.slice(8, 10));
  const hour = Number(text.slice(11, 13));
  const minute = Number(text.slice(14, 16));
  const second = text[16] === ":" ? Number(text.slice(17, 19)) : 0;
  const parts = [year, month, day, hour, minute, second];
  if (text[4] !== "-" || text[7] !== "-" || (text[10] !== "T" && text[10] !== " ")) {
    return null;
  }
  if (text[13] !== ":" || parts.some((part) => !Number.isInteger(part))) {
    return null;
  }
  return new Date(year, month - 1, day, hour, minute, second);
}

function formatWall(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    "-",
    pad(date.getMonth() + 1),
    "-",
    pad(date.getDate()),
    "T",
    pad(date.getHours()),
    ":",
    pad(date.getMinutes()),
    ":",
    pad(date.getSeconds()),
  ].join("");
}

function secondsOf(offset) {
  return offset.amount * (UNIT_MS[offset.unit] / 1000);
}

function offsetLabel(noun, offset) {
  const words = UNIT_WORDS[offset.unit];
  const unit = offset.amount === 1 ? words[0] : words[1];
  return `${noun} in ${offset.amount} ${unit}`;
}

function blankRule(rule) {
  if (!rule) {
    return true;
  }
  return !(
    (rule.start_offsets && rule.start_offsets.length)
    || rule.at_start
    || (rule.due_offsets && rule.due_offsets.length)
    || rule.at_due
    || rule.overdue
  );
}

function shift(moment, overdue) {
  if (overdue.kind === "daily_at") {
    const minute = overdue.minute_of_day || 0;
    const midnight = new Date(
      moment.getFullYear(),
      moment.getMonth(),
      moment.getDate(),
      0,
      0,
      0,
      0,
    );
    let candidate = new Date(midnight.getTime() + minute * 60000);
    if (candidate.getTime() <= moment.getTime()) {
      candidate = new Date(candidate.getTime() + DAY_MS);
    }
    return candidate;
  }
  return new Date(moment.getTime() + secondsOf(overdue) * 1000);
}

function timed(at, reason, now, catchUp, savedAt, rank) {
  if (at.getTime() > now.getTime()) {
    return [{ at, reason, catchUp: false, rank }];
  }
  if (catchUp && (savedAt == null || savedAt.getTime() < at.getTime())) {
    return [{ at, reason, catchUp: true, rank }];
  }
  return [];
}

function oneShots(kind, anchor, offsets, atAnchor, now, catchUp, savedAt) {
  const noun = kind === "start" ? "Starts" : "Due";
  const rank = kind === "start" ? 0 : 2;
  const found = [];
  (offsets || []).forEach((offset) => {
    const at = new Date(anchor.getTime() - secondsOf(offset) * 1000);
    found.push(...timed(at, offsetLabel(noun, offset), now, catchUp, savedAt, rank));
  });
  if (atAnchor) {
    found.push(...timed(anchor, `${noun} now`, now, catchUp, savedAt, rank + 1));
  }
  return found;
}

function overdueEvents(dueAt, overdue, now, snooze, dismissed, catchUp, savedAt, limit) {
  if (!overdue || dismissed || limit < 1) {
    return [];
  }
  const first = shift(dueAt, overdue);
  const events = [];
  let cursor;
  if (snooze && snooze.getTime() > now.getTime()) {
    cursor = snooze;
  } else if (snooze && snooze.getTime() <= now.getTime()) {
    if (catchUp) {
      events.push({ at: now, reason: "Overdue", catchUp: true, rank: 4 });
    }
    cursor = shift(now, overdue);
  } else if (first.getTime() <= now.getTime()) {
    if (catchUp && (savedAt == null || savedAt.getTime() < first.getTime())) {
      events.push({ at: now, reason: "Overdue", catchUp: true, rank: 4 });
    }
    cursor = shift(now, overdue);
  } else {
    cursor = first;
  }
  for (let index = 0; index < limit; index += 1) {
    events.push({ at: cursor, reason: "Overdue", catchUp: false, rank: 4 });
    cursor = shift(cursor, overdue);
  }
  return events;
}

function group(events) {
  const fires = [];
  events.forEach((event) => {
    const minute = new Date(
      event.at.getFullYear(),
      event.at.getMonth(),
      event.at.getDate(),
      event.at.getHours(),
      event.at.getMinutes(),
      0,
      0,
    ).getTime();
    const last = fires[fires.length - 1];
    if (
      last
      && last.catch_up === event.catchUp
      && last.minute === minute
    ) {
      if (!last.reasons.includes(event.reason)) {
        last.reasons.push(event.reason);
      }
      return;
    }
    fires.push({
      at: formatWall(event.at),
      reasons: [event.reason],
      catch_up: event.catchUp,
      minute,
    });
  });
  return fires.map(({ minute, ...fire }) => fire);
}

function planFires(input) {
  const rule = input.rule || {};
  if (input.closed || blankRule(rule)) {
    return [];
  }
  const now = parseWall(input.now);
  const savedAt = parseWall(input.rule_updated_at);
  const events = [];
  const startAt = parseWall(input.start_at);
  const dueAt = parseWall(input.due_at);
  if (startAt) {
    events.push(...oneShots(
      "start",
      startAt,
      rule.start_offsets,
      rule.at_start,
      now,
      Boolean(input.catch_up),
      savedAt,
    ));
  }
  if (dueAt) {
    events.push(...oneShots(
      "due",
      dueAt,
      rule.due_offsets,
      rule.at_due,
      now,
      Boolean(input.catch_up),
      savedAt,
    ));
    events.push(...overdueEvents(
      dueAt,
      rule.overdue,
      now,
      parseWall(input.snooze_until),
      Boolean(input.overdue_dismissed),
      Boolean(input.catch_up),
      savedAt,
      Number(input.overdue_limit || 32),
    ));
  }
  events.sort((left, right) => {
    const time = left.at.getTime() - right.at.getTime();
    if (time) {
      return time;
    }
    if (left.catchUp !== right.catchUp) {
      return left.catchUp ? 1 : -1;
    }
    return left.rank - right.rank;
  });
  return group(events);
}

function closed(issue) {
  return issue.status === "done" || issue.status === "cancelled";
}

function resolveRule(issue, reminders) {
  const own = (reminders.issueRules || []).find((rule) => rule.issue_id === issue.id);
  if (own) {
    return { source: "issue", rule: own };
  }
  if (issue.series_id) {
    const series = (reminders.seriesRules || []).find(
      (rule) => rule.series_id === issue.series_id,
    );
    if (series) {
      return { source: "series", rule: series };
    }
  }
  if (reminders.defaultRule) {
    return { source: "default", rule: reminders.defaultRule };
  }
  return { source: "none", rule: null };
}

function firesForIssues(issues, reminders, now, catchUp) {
  const found = [];
  (issues || []).forEach((issue) => {
    if (!issue || closed(issue)) {
      return;
    }
    const resolved = resolveRule(issue, reminders);
    if (!resolved.rule || blankRule(resolved.rule)) {
      return;
    }
    const state = (reminders.states || []).find((row) => row.issue_id === issue.id);
    planFires({
      now: formatWall(now),
      start_at: issue.start_at,
      due_at: issue.due_at,
      catch_up: catchUp,
      rule_updated_at: resolved.rule.updated_at,
      snooze_until: state && state.snooze_until,
      overdue_dismissed: state && state.overdue_dismissed,
      rule: resolved.rule,
    }).forEach((fire) => {
      found.push({
        ...fire,
        issue_id: issue.id,
        issue_key: issue.key,
        issue_title: issue.title,
      });
    });
  });
  return found;
}

function deliveryKey(fire) {
  return `${fire.issue_id}|${fire.at}|${fire.reasons.join("|")}`;
}

function withBag(store, mutate) {
  const next = JSON.parse(JSON.stringify(store));
  next.reminders = next.reminders || emptyBag();
  mutate(next.reminders);
  return next;
}

function ruleList(reminders, scope) {
  if (scope === "default") {
    return reminders.defaultRule ? [reminders.defaultRule] : [];
  }
  return scope === "series" ? reminders.seriesRules : reminders.issueRules;
}

function putRule(store, scope, ids, body, nowIso) {
  return withBag(store, (reminders) => {
    const list = ruleList(reminders, scope);
    const current = list.find((rule) => matches(rule, scope, ids));
    const base = current && !current.pending ? current.updated_at : (current && current.base_updated_at) || null;
    const saved = {
      ...(current || {}),
      ...body,
      scope,
      series_id: ids.seriesId || null,
      issue_id: ids.issueId || null,
      pending: true,
      base_updated_at: base,
      updated_at: nowIso,
      conflict: null,
    };
    if (scope === "default") {
      reminders.defaultRule = saved;
    } else if (scope === "series") {
      reminders.seriesRules = list.filter((rule) => rule.series_id !== ids.seriesId).concat(saved);
    } else {
      reminders.issueRules = list.filter((rule) => rule.issue_id !== ids.issueId).concat(saved);
    }
    const id = queueId(scope, ids, "put");
    reminders.queue = reminders.queue.filter((item) => item.id !== id);
    reminders.queue.push({
      id,
      kind: "rule",
      method: "PUT",
      path: rulePath(scope, ids),
      body: { ...body, base_updated_at: base },
      issueId: ids.issueId || null,
      seriesId: ids.seriesId || null,
      conflict: null,
    });
  });
}

function deleteRule(store, scope, ids) {
  return withBag(store, (reminders) => {
    const list = ruleList(reminders, scope);
    const current = list.find((rule) => matches(rule, scope, ids));
    const base = current ? (current.pending ? current.base_updated_at : current.updated_at) : null;
    if (scope === "default") {
      reminders.defaultRule = null;
    } else if (scope === "series") {
      reminders.seriesRules = list.filter((rule) => rule.series_id !== ids.seriesId);
    } else {
      reminders.issueRules = list.filter((rule) => rule.issue_id !== ids.issueId);
    }
    const id = queueId(scope, ids, "delete");
    reminders.queue = reminders.queue.filter(
      (item) => item.id !== id && item.id !== queueId(scope, ids, "put"),
    );
    if (!base) {
      return;
    }
    reminders.queue.push({
      id,
      kind: "rule",
      method: "DELETE",
      path: `${rulePath(scope, ids)}?base_updated_at=${encodeURIComponent(base)}`,
      body: null,
      issueId: ids.issueId || null,
      seriesId: ids.seriesId || null,
      conflict: null,
    });
  });
}

function queueState(store, issueId, kind, body) {
  return withBag(store, (reminders) => {
    const current = (reminders.states || []).find((row) => row.issue_id === issueId);
    const base = current ? current.updated_at : null;
    const next = {
      issue_id: issueId,
      snooze_until: current && current.snooze_until,
      overdue_dismissed: current ? current.overdue_dismissed : false,
      updated_at: body.now || (current && current.updated_at) || null,
      pending: true,
    };
    if (kind === "snooze") {
      next.snooze_until = body.until;
    }
    if (kind === "dismiss") {
      next.overdue_dismissed = true;
    }
    if (kind === "resume") {
      next.overdue_dismissed = false;
    }
    reminders.states = (reminders.states || []).filter((row) => row.issue_id !== issueId).concat(next);
    const id = `state-${issueId}-${kind}`;
    reminders.queue = reminders.queue.filter((item) => item.id !== id);
    const path = kind === "snooze"
      ? `/api/v1/issues/${issueId}/reminder/snooze`
      : `/api/v1/issues/${issueId}/reminder/${kind === "dismiss" ? "dismiss-overdue" : "resume-overdue"}`;
    const payload = kind === "snooze"
      ? { until: body.until, base_updated_at: base }
      : { base_updated_at: base };
    reminders.queue.push({
      id,
      kind: "state",
      method: kind === "snooze" ? "PUT" : "POST",
      path,
      body: payload,
      issueId,
      seriesId: null,
      conflict: null,
    });
  });
}

function matches(rule, scope, ids) {
  if (scope === "series") {
    return rule.series_id === ids.seriesId;
  }
  if (scope === "issue") {
    return rule.issue_id === ids.issueId;
  }
  return true;
}

function queueId(scope, ids, kind) {
  return `${kind}-${scope}-${ids.seriesId || ""}-${ids.issueId || ""}`;
}

function rulePath(scope, ids) {
  if (scope === "default") {
    return "/api/v1/profile/reminders";
  }
  if (scope === "series") {
    return `/api/v1/series/${ids.seriesId}/reminder`;
  }
  return `/api/v1/issues/${ids.issueId}/reminder`;
}

function retargetIssue(store, fromId, toId) {
  if (!store.reminders || fromId === toId) {
    return store;
  }
  return withBag(store, (reminders) => {
    reminders.issueRules.forEach((rule) => {
      if (rule.issue_id === fromId) {
        rule.issue_id = toId;
      }
    });
    reminders.states.forEach((row) => {
      if (row.issue_id === fromId) {
        row.issue_id = toId;
      }
    });
    reminders.queue.forEach((item) => {
      if (item.issueId !== fromId) {
        return;
      }
      item.issueId = toId;
      const query = item.path.includes("?") ? item.path.slice(item.path.indexOf("?")) : "";
      if (item.kind === "state") {
        const action = item.path.includes("/snooze")
          ? "snooze"
          : (item.path.includes("resume-overdue") ? "resume" : "dismiss");
        item.id = `state-${toId}-${action}`;
        item.path = action === "snooze"
          ? `/api/v1/issues/${toId}/reminder/snooze`
          : `/api/v1/issues/${toId}/reminder/${action === "dismiss" ? "dismiss-overdue" : "resume-overdue"}`;
      } else {
        item.id = queueId("issue", { issueId: toId }, item.method === "DELETE" ? "delete" : "put");
        item.path = `${rulePath("issue", { issueId: toId })}${query}`;
      }
    });
  });
}

function retargetSeries(store, fromId, toId) {
  if (!store.reminders || !toId || fromId === toId) {
    return store;
  }
  return withBag(store, (reminders) => {
    reminders.seriesRules.forEach((rule) => {
      if (rule.series_id === fromId) {
        rule.series_id = toId;
      }
    });
    reminders.queue.forEach((item) => {
      if (item.seriesId !== fromId) {
        return;
      }
      item.seriesId = toId;
      const query = item.path.includes("?") ? item.path.slice(item.path.indexOf("?")) : "";
      item.id = queueId("series", { seriesId: toId }, item.method === "DELETE" ? "delete" : "put");
      item.path = `${rulePath("series", { seriesId: toId })}${query}`;
    });
  });
}

function absorbRules(store, remote) {
  if (!remote) {
    return store;
  }
  return withBag(store, (reminders) => {
    const pendingDefault = reminders.defaultRule && reminders.defaultRule.pending;
    if (!pendingDefault) {
      reminders.defaultRule = remote.default || null;
    }
    reminders.seriesRules = mergeRules(reminders.seriesRules, remote.series || [], "series_id");
    reminders.issueRules = mergeRules(reminders.issueRules, remote.issues || [], "issue_id");
    const pendingStates = new Set(
      (reminders.states || []).filter((row) => row.pending).map((row) => row.issue_id),
    );
    const kept = (reminders.states || []).filter((row) => pendingStates.has(row.issue_id));
    const incoming = (remote.states || []).filter((row) => !pendingStates.has(row.issue_id));
    reminders.states = kept.concat(incoming);
  });
}

function mergeRules(local, remote, key) {
  const pending = new Set(local.filter((rule) => rule.pending || rule.conflict).map((rule) => rule[key]));
  return local.filter((rule) => pending.has(rule[key])).concat(
    remote.filter((rule) => !pending.has(rule[key])),
  );
}

async function uploadReminderQueue(store, client) {
  if (!store.reminders || !(store.reminders.queue || []).length) {
    return store;
  }
  let current = store;
  for (const original of store.reminders.queue) {
    const item = (current.reminders.queue || []).find((entry) => entry.id === original.id);
    if (!item || item.conflict) {
      continue;
    }
    if ((item.issueId != null && item.issueId < 0) || (item.seriesId != null && item.seriesId < 0)) {
      continue;
    }
    try {
      const saved = await client.send(item.method, item.path, item.body);
      current = finishUpload(current, item, saved);
    } catch (error) {
      if (error.status === 0 || error.status === 401) {
        throw error;
      }
      if (error.status === 404 && item.method === "DELETE") {
        current = finishUpload(current, item, null);
        continue;
      }
      if (error.status === 409) {
        current = withBag(current, (reminders) => {
          const queued = reminders.queue.find((entry) => entry.id === item.id);
          if (queued) {
            const detail = error.body && error.body.detail;
            queued.conflict = (detail && detail.context && detail.context.server) || { deleted: true };
          }
        });
      }
    }
  }
  return current;
}

function finishUpload(store, item, saved) {
  return withBag(store, (reminders) => {
    reminders.queue = reminders.queue.filter((entry) => entry.id !== item.id);
    if (item.path.indexOf("/snooze") >= 0 || item.path.indexOf("overdue") >= 0) {
      reminders.states = (reminders.states || []).map((row) => (
        row.issue_id === item.issueId ? { ...saved, pending: false } : row
      ));
      return;
    }
    const clearPending = (rule) => (rule ? { ...rule, ...saved, pending: false, conflict: null } : rule);
    if (item.path.indexOf("/profile/") >= 0) {
      reminders.defaultRule = item.method === "DELETE" ? null : clearPending(reminders.defaultRule);
    } else if (item.path.indexOf("/series/") >= 0) {
      if (item.method === "DELETE") {
        reminders.seriesRules = reminders.seriesRules.filter((rule) => rule.series_id !== item.seriesId);
      } else {
        reminders.seriesRules = reminders.seriesRules.map((rule) => (
          rule.series_id === item.seriesId ? clearPending(rule) : rule
        ));
      }
    } else if (item.method === "DELETE") {
      reminders.issueRules = reminders.issueRules.filter((rule) => rule.issue_id !== item.issueId);
    } else {
      reminders.issueRules = reminders.issueRules.map((rule) => (
        rule.issue_id === item.issueId ? clearPending(rule) : rule
      ));
    }
  });
}

function chooseReminderPhone(store, queueIdValue) {
  return withBag(store, (reminders) => {
    const item = reminders.queue.find((entry) => entry.id === queueIdValue);
    if (!item || !item.conflict || item.conflict.deleted) {
      if (item && item.conflict && item.conflict.deleted) {
        item.body = { ...(item.body || {}), base_updated_at: null };
        item.conflict = null;
      }
      return;
    }
    item.body = { ...(item.body || {}), base_updated_at: item.conflict.updated_at };
    item.conflict = null;
  });
}

function chooseReminderServer(store, queueIdValue) {
  return withBag(store, (reminders) => {
    const item = reminders.queue.find((entry) => entry.id === queueIdValue);
    if (!item) {
      return;
    }
    reminders.queue = reminders.queue.filter((entry) => entry.id !== item.id);
    const server = item.conflict;
    if (item.kind === "state") {
      if (!server || server.deleted) {
        reminders.states = reminders.states.filter((row) => row.issue_id !== item.issueId);
      } else {
        reminders.states = reminders.states
          .filter((row) => row.issue_id !== item.issueId)
          .concat({ ...server, pending: false });
      }
      return;
    }
    if (!server || server.deleted) {
      if (item.path.indexOf("/profile/") >= 0) {
        reminders.defaultRule = null;
      } else if (item.seriesId) {
        reminders.seriesRules = reminders.seriesRules.filter((rule) => rule.series_id !== item.seriesId);
      } else if (item.issueId) {
        reminders.issueRules = reminders.issueRules.filter((rule) => rule.issue_id !== item.issueId);
      }
      return;
    }
    const adopted = { ...server, pending: false, conflict: null };
    if (item.path.indexOf("/profile/") >= 0) {
      reminders.defaultRule = adopted;
    } else if (item.seriesId) {
      reminders.seriesRules = reminders.seriesRules.filter((rule) => rule.series_id !== item.seriesId).concat(adopted);
    } else if (server.issue_id) {
      reminders.issueRules = reminders.issueRules.filter((rule) => rule.issue_id !== server.issue_id).concat(adopted);
    }
  });
}

function savedIssues(store) {
  const issues = [];
  Object.values((store && store.projects) || {}).forEach((project) => {
    if (project.enabled === false) {
      return;
    }
    Object.values(project.issues || {}).forEach((record) => {
      if (record.raw) {
        issues.push(record.raw);
      }
    });
  });
  return issues;
}

function markDelivered(store, fires) {
  return withBag(store, (reminders) => {
    fires.forEach((fire) => {
      reminders.delivered[deliveryKey(fire)] = true;
    });
  });
}

function unseenCatchUps(fires, reminders) {
  const delivered = (reminders && reminders.delivered) || {};
  return fires.filter((fire) => fire.catch_up && !delivered[deliveryKey(fire)]);
}

function reminderIsOn(issue, reminders) {
  const resolved = resolveRule(issue, reminders || emptyBag());
  return !blankRule(resolved.rule);
}

function reminderConflict(reminders, scope, ids) {
  const put = queueId(scope, ids, "put");
  const removed = queueId(scope, ids, "delete");
  return (reminders.queue || []).find(
    (item) => (item.id === put || item.id === removed) && item.conflict,
  ) || null;
}

function clockFromMinute(minute) {
  const hour = Math.floor(Number(minute) / 60);
  const rest = Number(minute) % 60;
  const pad = (value) => String(value).padStart(2, "0");
  return `${pad(hour)}:${pad(rest)}`;
}

function formFromRule(rule) {
  const overdue = rule && rule.overdue;
  const rows = (offsets) => (
    offsets && offsets.length ? offsets.map((offset) => ({ ...offset })) : [{ amount: "", unit: "hour" }]
  );
  return {
    startRows: rows(rule && rule.start_offsets),
    dueRows: rows(rule && rule.due_offsets),
    atStart: Boolean(rule && rule.at_start),
    atDue: Boolean(rule && rule.at_due),
    overdueKind: overdue ? overdue.kind : "off",
    overdueAmount: overdue && overdue.amount ? String(overdue.amount) : "30",
    overdueUnit: (overdue && overdue.unit) || "minute",
    overdueClock: overdue && overdue.minute_of_day != null ? clockFromMinute(overdue.minute_of_day) : "09:00",
  };
}

function bodyFromForm(form) {
  const offsets = (list) => list
    .map((row) => ({ amount: Number(row.amount), unit: row.unit }))
    .filter((row) => Number.isInteger(row.amount) && row.amount >= 1 && UNIT_MS[row.unit]);
  const body = {
    start_offsets: offsets(form.startRows || []),
    at_start: Boolean(form.atStart),
    due_offsets: offsets(form.dueRows || []),
    at_due: Boolean(form.atDue),
    overdue: null,
  };
  if (form.overdueKind === "every_n") {
    const amount = Number(form.overdueAmount);
    if (!Number.isInteger(amount) || amount < 1 || !UNIT_MS[form.overdueUnit]) {
      return { error: "Overdue needs an amount of at least 1." };
    }
    body.overdue = { kind: "every_n", amount, unit: form.overdueUnit };
  } else if (form.overdueKind === "daily_at") {
    const matched = /^(\d{1,2}):(\d{2})$/.exec(String(form.overdueClock || ""));
    if (!matched) {
      return { error: "Overdue needs a time like 09:00." };
    }
    const minute = Number(matched[1]) * 60 + Number(matched[2]);
    if (minute < 0 || minute >= 1440) {
      return { error: "Overdue needs a time like 09:00." };
    }
    body.overdue = { kind: "daily_at", minute_of_day: minute };
  }
  return { body };
}

function snoozeStamp(value) {
  const matched = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/.exec(String(value || "").trim());
  if (!matched) {
    return null;
  }
  return `${matched[1]}T${matched[2]}:00`;
}

module.exports = {
  absorbRules,
  bag,
  chooseReminderPhone,
  chooseReminderServer,
  deleteRule,
  deliveryKey,
  bodyFromForm,
  emptyBag,
  firesForIssues,
  formFromRule,
  formatWall,
  markDelivered,
  parseWall,
  planFires,
  putRule,
  queueState,
  reminderConflict,
  reminderIsOn,
  resolveRule,
  retargetIssue,
  retargetSeries,
  savedIssues,
  snoozeStamp,
  unseenCatchUps,
  uploadReminderQueue,
};
