// Switches the acting user as soon as the dropdown changes. The Switch button
// stays in the markup and is hidden by CSS once this marker is set, so the form
// still works when this script does not run.
(() => {
  document.documentElement.setAttribute("data-keel-js", "on");

  const form = document.querySelector(".keel-userpicker");
  const select = form && form.querySelector("select");
  if (!select) {
    return;
  }

  select.addEventListener("change", () => {
    form.submit();
  });
})();
