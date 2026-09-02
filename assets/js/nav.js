// Lets section links be dragged in the top bar. Up/Down forms stay in the
// markup and are hidden only after this script has run, so the order can still
// change when JavaScript does not load.
(() => {
  document.documentElement.setAttribute("data-keel-nav", "on");

  const root = document.querySelector("[data-keel-nav-root]");
  if (!root) {
    return;
  }

  const items = () => [...root.querySelectorAll("[data-keel-nav-item]")];

  const save = () => {
    const order = items()
      .map((item) => item.dataset.keelNavItem)
      .join(",");
    fetch("/web/nav", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ order, next: location.pathname }),
      redirect: "manual",
    });
  };

  let dragged = false;

  for (const item of items()) {
    const handle = item.querySelector("[data-keel-nav-handle]");
    if (!handle) {
      continue;
    }
    handle.setAttribute("draggable", "true");
    handle.addEventListener("dragstart", (event) => {
      event.dataTransfer.setData("text/plain", item.dataset.keelNavItem);
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
      const moving = root.querySelector(`[data-keel-nav-item="${key}"]`);
      if (!moving || moving === item) {
        return;
      }
      root.insertBefore(moving, item);
      save();
    });
  }

  root.addEventListener("dragover", (event) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  });
  root.addEventListener("drop", (event) => {
    event.preventDefault();
    const key = event.dataTransfer.getData("text/plain");
    const moving = root.querySelector(`[data-keel-nav-item="${key}"]`);
    if (!moving) {
      return;
    }
    root.appendChild(moving);
    save();
  });
})();
