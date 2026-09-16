// Opens the issue repeating recipe as a modal overlay. The Make this repeating
// and Edit series controls stay real links (`?repeat=1`), and Cancel/Close stay
// links back to the issue, so the overlay works when this script does not run.
(() => {
  const dialog = document.querySelector("[data-keel-overlay]");
  if (!(dialog instanceof HTMLDialogElement)) {
    return;
  }
  if (typeof dialog.showModal !== "function") {
    return;
  }

  document.documentElement.setAttribute("data-keel-overlay-js", "on");

  const stripOpenQuery = () => {
    const url = new URL(window.location.href);
    if (url.searchParams.get("repeat") !== "1") {
      return;
    }
    url.searchParams.delete("repeat");
    url.searchParams.delete("error");
    const query = url.searchParams.toString();
    history.replaceState(null, "", url.pathname + (query ? `?${query}` : ""));
  };

  const openOverlay = (event) => {
    event.preventDefault();
    if (dialog.open) {
      return;
    }
    dialog.showModal();
  };

  const closeOverlay = (event) => {
    event.preventDefault();
    dialog.close();
  };

  for (const opener of document.querySelectorAll("[data-keel-overlay-open]")) {
    opener.addEventListener("click", openOverlay);
  }
  for (const closer of dialog.querySelectorAll("[data-keel-overlay-close]")) {
    closer.addEventListener("click", closeOverlay);
  }

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });

  dialog.addEventListener("close", stripOpenQuery);

  if (dialog.hasAttribute("open")) {
    dialog.removeAttribute("open");
    dialog.showModal();
  }
})();
