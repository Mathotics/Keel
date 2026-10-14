const { findIssue, markConflict, markError, noteUploaded } = require("./offline");

function restoreComment(store, item) {
  if (!item.comment) {
    return store;
  }
  const copy = JSON.parse(JSON.stringify(store));
  const issue = findIssue(copy, item.issueId);
  if (!issue || !issue.page) {
    return store;
  }
  const comments = issue.page.comments || [];
  if (!comments.some((comment) => comment.id === item.comment.id)) {
    issue.page.comments = [...comments, item.comment];
  }
  return copy;
}

async function uploadQueue(store, client) {
  let current = store;
  const held = new Set();
  for (const original of store.queue) {
    const item = (current.queue || []).find((entry) => entry.id === original.id);
    if (!item) {
      continue;
    }
    if (held.has(item.issueId) || held.has(original.issueId)) {
      continue;
    }
    const record = current.projects[item.projectId]
      && current.projects[item.projectId].issues[item.issueId];
    if (record && record.conflict) {
      held.add(item.issueId);
      continue;
    }
    if (item.kind !== "create" && item.kind !== "comment" && item.kind !== "uncomment") {
      let server;
      try {
        server = await client.read(`/api/v1/issues/${item.issueId}`);
      } catch (error) {
        if (error.status === 0) {
          throw error;
        }
        if (error.status === 404) {
          if (item.kind === "delete") {
            current = noteUploaded(current, item, null);
            continue;
          }
          current = markConflict(current, item.issueId, { kind: "deleted" });
        } else {
          current = markError(current, item.issueId, error.message);
        }
        held.add(item.issueId);
        continue;
      }
      if (!item.force && server.updated_at !== item.baseUpdatedAt) {
        current = markConflict(current, item.issueId, { kind: "changed", server });
        held.add(item.issueId);
        continue;
      }
    }
    try {
      const saved = await client.send(item.method, item.path, item.body);
      current = noteUploaded(current, item, saved);
    } catch (error) {
      if (error.status === 0) {
        throw error;
      }
      if (item.kind === "uncomment" && error.status === 404) {
        current = noteUploaded(current, item, null);
        continue;
      }
      if (item.kind === "uncomment") {
        current = restoreComment(current, item);
      }
      current = markError(current, item.issueId, error.message);
      held.add(item.issueId);
    }
  }
  return current;
}

async function pullLibrary(store, client) {
  const profile = await client.profile();
  const uploaded = await uploadQueue(store, client);
  const snapshots = await client.snapshots();
  const catalog = await client.catalog();
  const { applyRefresh } = require("./offline");
  return {
    userId: profile.id,
    store: applyRefresh(uploaded, snapshots, catalog),
  };
}

module.exports = {
  pullLibrary,
  uploadQueue,
};
