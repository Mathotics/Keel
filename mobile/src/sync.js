const { emptyStore, markConflict, markError, noteUploaded } = require("./offline");

async function uploadQueue(store, client) {
  let current = store;
  const held = new Set();
  for (const item of store.queue) {
    if (held.has(item.issueId)) {
      continue;
    }
    const record = current.projects[item.projectId]
      && current.projects[item.projectId].issues[item.issueId];
    if (record && record.conflict) {
      held.add(item.issueId);
      continue;
    }
    if (item.kind !== "create") {
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
