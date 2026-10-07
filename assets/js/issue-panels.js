// Persists which issue-page panels are collapsed. Minimize/Expand stays in
// the markup and is hidden only after this script has run.
(() => {
  const panels = [...document.querySelectorAll("[data-keel-issue-panel]")];
  if (!panels.length) {
    return;
  }
  document.documentElement.setAttribute("data-keel-issue-panels", "on");

  const save = () => {
    const collapsed = panels
      .filter((panel) => !panel.open)
      .map((panel) => panel.dataset.keelIssuePanel)
      .filter(Boolean)
      .join(".");
    const next = window.location.pathname + window.location.search;
    fetch("/web/issue-panels", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ collapsed, next }),
      redirect: "manual",
    });
  };

  for (const panel of panels) {
    panel.addEventListener("toggle", save);
  }
})();
