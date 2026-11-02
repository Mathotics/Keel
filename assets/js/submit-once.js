// Ignores a second submit of a create form. The hidden client_key is what
// keeps a double post to one issue when this script has not run.
document.documentElement.setAttribute("data-keel-once", "");

for (const form of document.querySelectorAll("[data-keel-submit-once]")) {
  form.addEventListener("submit", (event) => {
    if (form.getAttribute("data-keel-submitted") === "1") {
      event.preventDefault();
      return;
    }
    form.setAttribute("data-keel-submitted", "1");
  });
}
