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
})();
