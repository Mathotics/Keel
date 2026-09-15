// Submits the user picker and any `[data-keel-autosubmit]` form as soon as a
// control changes. Fallback submit buttons stay in the markup and are hidden
// by CSS once this marker is set, so the forms still work when this script
// does not run. Type dropdowns keep `data-type` matched to the selected value.
// Paired `[data-keel-range]` date fields keep min/max in sync so a sprint
// cannot pick an end before its start.
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

  for (const select of document.querySelectorAll("select.keel-type-select")) {
    const sync = () => {
      select.dataset.type = select.value;
    };
    select.addEventListener("change", sync);
    sync();
  }

  for (const form of document.querySelectorAll("form")) {
    const start = form.querySelector("[data-keel-range='start']");
    const end = form.querySelector("[data-keel-range='end']");
    if (!start || !end) {
      continue;
    }
    const sync = () => {
      end.min = start.value;
      start.max = end.value;
    };
    start.addEventListener("input", sync);
    end.addEventListener("input", sync);
    sync();
  }
})();
