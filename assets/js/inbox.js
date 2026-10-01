// Persists which home inbox sections are collapsed. Minimize/Expand forms stay
// in the markup and are hidden only after this script has run, so the choice
// can still be saved when JavaScript does not load.
(() => {
  document.documentElement.setAttribute("data-keel-inbox", "on");

  const panels = [...document.querySelectorAll("[data-keel-inbox-panel]")];
  if (!panels.length) {
    return;
  }

  const save = () => {
    const collapsed = panels
      .filter((panel) => !panel.open)
      .map((panel) => panel.dataset.keelInboxPanel)
      .filter(Boolean)
      .join(".");
    fetch("/web/inbox", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ collapsed, next: "/" }),
      redirect: "manual",
    });
  };

  for (const panel of panels) {
    panel.addEventListener("toggle", save);
  }

  const root = document.querySelector("[data-keel-home-root]");
  if (!root) {
    return;
  }

  const items = () => [...root.querySelectorAll("[data-keel-home-item]")];

  const saveOrder = () => {
    const order = items()
      .map((item) => item.dataset.keelHomeItem)
      .filter(Boolean)
      .join(",");
    fetch("/web/home/order", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ order, next: "/" }),
      redirect: "manual",
    });
  };

  let dragged = false;

  for (const item of items()) {
    const handle = item.querySelector("h2");
    if (!handle) {
      continue;
    }
    handle.setAttribute("data-keel-home-handle", "");
    handle.setAttribute("draggable", "true");
    handle.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", item.dataset.keelHomeItem);
      event.dataTransfer.effectAllowed = "move";
      item.classList.add("is-dragging");
      dragged = true;
    });
    handle.addEventListener("dragend", () => {
      item.classList.remove("is-dragging");
      for (const other of items()) {
        other.classList.remove("is-drop-target");
      }
    });
    handle.addEventListener("click", (event) => {
      if (!dragged) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      dragged = false;
    });
  }

  for (const item of items()) {
    item.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      item.classList.add("is-drop-target");
    });
    item.addEventListener("dragleave", () => {
      item.classList.remove("is-drop-target");
    });
    item.addEventListener("drop", (event) => {
      event.preventDefault();
      event.stopPropagation();
      item.classList.remove("is-drop-target");
      const key = event.dataTransfer.getData("text/plain");
      const moving = root.querySelector(`[data-keel-home-item="${key}"]`);
      if (!moving || moving === item) {
        return;
      }
      root.insertBefore(moving, item);
      saveOrder();
    });
  }
})();
