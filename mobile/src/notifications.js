const EMPTY = "There are no notifications.";
const PHONE_NOTE = "Phone alert is saved here. The Android notification is sent in a later update.";

const TYPES = [
  ["comment_on_created", "Comment on an issue you created"],
  ["comment_on_assigned", "Comment on an issue assigned to you"],
  ["assigned", "Someone assigns an issue to you"],
  ["update_on_created", "Update to an issue you created"],
  ["update_on_assigned", "Update to an issue assigned to you"],
  ["delete_on_created", "Deletion of an issue you created"],
  ["delete_on_assigned", "Deletion of an issue assigned to you"],
];

function appBarSlots() {
  return ["connection", "bell", "profile"];
}

function bellState(notices) {
  const unread = (notices || []).some((notice) => notice && !notice.read_at);
  return {
    dot: unread,
    label: unread ? "Notifications, unread" : "Notifications",
  };
}

function compareNotices(left, right) {
  const created = String(right.created_at || "").localeCompare(String(left.created_at || ""));
  if (created) {
    return created;
  }
  return (right.id || 0) - (left.id || 0);
}

function presentNotice(notice) {
  const key = notice.issue_key || "";
  const title = notice.issue_title || "";
  return {
    id: notice.id,
    actorName: notice.actor_name || "",
    issueId: notice.issue_id == null ? null : notice.issue_id,
    issueKey: key,
    issueTitle: title,
    heading: `${key} ${title}`.trim(),
    body: notice.body || "",
    createdAt: notice.created_at || "",
    unread: !notice.read_at,
    linked: notice.issue_id != null,
  };
}

function noticeList(notices) {
  const rows = (notices || []).slice().sort(compareNotices).map(presentNotice);
  return {
    empty: rows.length ? "" : EMPTY,
    rows,
  };
}

function openNotice(notice) {
  if (!notice) {
    return { missing: true };
  }
  const issueId = notice.issueId != null
    ? notice.issueId
    : (notice.issue_id == null ? null : notice.issue_id);
  return {
    readIds: [notice.id],
    issueId,
  };
}

function viewedNotices(notices) {
  return (notices || []).filter((notice) => notice && !notice.read_at).map((notice) => notice.id);
}

function withoutNotice(notices, id) {
  return (notices || []).filter((notice) => notice.id !== id);
}

function mergeInbox(cached, server, online) {
  if (online && Array.isArray(server)) {
    return server;
  }
  return Array.isArray(cached) ? cached : [];
}

function preferenceRows(stored) {
  const byType = {};
  for (const row of stored || []) {
    if (row && row.type) {
      byType[row.type] = row;
    }
  }
  return TYPES.map(([type, label]) => {
    const row = byType[type];
    return {
      type,
      label,
      email: Boolean(row && row.email),
      phone: Boolean(row && row.phone),
      bell: row ? Boolean(row.bell) : true,
    };
  });
}

function preferenceBody(rows) {
  return {
    preferences: (rows || []).map((row) => ({
      type: row.type,
      email: Boolean(row.email),
      phone: Boolean(row.phone),
      bell: Boolean(row.bell),
    })),
  };
}

function togglePreference(rows, type, channel) {
  return (rows || []).map((row) => (
    row.type === type ? { ...row, [channel]: !row[channel] } : row
  ));
}

function noticeCacheKey(userId) {
  return `keel.notices.${userId}`;
}

module.exports = {
  EMPTY,
  PHONE_NOTE,
  appBarSlots,
  bellState,
  mergeInbox,
  noticeCacheKey,
  noticeList,
  openNotice,
  preferenceBody,
  preferenceRows,
  togglePreference,
  viewedNotices,
  withoutNotice,
};
