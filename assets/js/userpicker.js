// Submits the user picker and any `[data-keel-autosubmit]` form as soon as a
// control changes. Fallback submit buttons stay in the markup and are hidden
// by CSS once this marker is set, so the forms still work when this script
// does not run.
(() => {
  document.documentElement.setAttribute("data-keel-js", "on");

  const listen = (form) => {
    form.addEventListener("change", () => {
      form.submit();
    });
  };

  const picker = document.querySelector(".keel-userpicker");
  if (picker) {
    listen(picker);
  }

  for (const form of document.querySelectorAll("[data-keel-autosubmit]")) {
    listen(form);
  }
})();
