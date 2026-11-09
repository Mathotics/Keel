// Refreshes the unread dot when the page opens and about every 30 seconds.
(() => {
  const dot = document.querySelector("[data-keel-bell-dot]");
  if (!dot) {
    return;
  }
  const bell = dot.closest("a");
  const pollMs = 30000;

  const refresh = () => {
    fetch("/api/v1/notifications", { headers: { Accept: "application/json" } })
      .then((response) => (response.ok ? response.json() : null))
      .then((notices) => {
        if (!Array.isArray(notices)) {
          return;
        }
        const unread = notices.some((notice) => !notice.read_at);
        dot.hidden = !unread;
        if (bell) {
          bell.setAttribute(
            "aria-label",
            unread ? "Notifications, unread" : "Notifications",
          );
        }
      })
      .catch(() => {});
  };

  refresh();
  setInterval(refresh, pollMs);
})();
