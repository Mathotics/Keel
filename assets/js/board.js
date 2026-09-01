// Marks cards draggable and PATCHes status on drop. The per-card Move form
// stays in the markup and is hidden only after this script has run, so a card
// can still change column when JavaScript does not load.
(() => {
  document.documentElement.setAttribute("data-keel-board", "on");

  const board = document.querySelector("[data-keel-board-root]");
  if (!board) {
    return;
  }

  const banner = board.querySelector("[data-keel-board-error]");

  const showError = (message) => {
    if (!banner) {
      return;
    }
    banner.hidden = false;
    banner.textContent = message;
  };

  const clearError = () => {
    if (!banner) {
      return;
    }
    banner.hidden = true;
    banner.textContent = "";
  };

  const recount = () => {
    for (const column of board.querySelectorAll("[data-status]")) {
      const badge = column.querySelector("[data-keel-count]");
      if (badge) {
        badge.textContent = String(column.querySelectorAll("[data-issue-id]").length);
      }
    }
  };

  const messageFrom = async (response) => {
    try {
      const body = await response.json();
      if (body && body.detail && body.detail.message) {
        return body.detail.message;
      }
    } catch (_error) {
      // The server sometimes answers with an empty or non-JSON body.
    }
    return "That move could not be saved.";
  };

  for (const card of board.querySelectorAll("[data-issue-id]")) {
    card.setAttribute("draggable", "true");
    card.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", card.dataset.issueId);
      event.dataTransfer.effectAllowed = "move";
      card.classList.add("is-dragging");
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("is-dragging");
    });
  }

  for (const column of board.querySelectorAll("[data-status]")) {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      column.classList.add("is-drop-target");
    });
    column.addEventListener("dragleave", () => {
      column.classList.remove("is-drop-target");
    });
    column.addEventListener("drop", async (event) => {
      event.preventDefault();
      column.classList.remove("is-drop-target");
      const issueId = event.dataTransfer.getData("text/plain");
      const card = board.querySelector(`[data-issue-id="${issueId}"]`);
      if (!card) {
        return;
      }
      const home = card.closest("[data-status]");
      if (home === column) {
        return;
      }
      const destination = column.querySelector("[data-keel-cards]");
      destination.appendChild(card);
      try {
        const response = await fetch(`/api/v1/issues/${issueId}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: column.dataset.status }),
        });
        if (!response.ok) {
          throw new Error(await messageFrom(response));
        }
        recount();
        clearError();
      } catch (error) {
        home.querySelector("[data-keel-cards]").appendChild(card);
        showError(error.message);
      }
    });
  }
})();
