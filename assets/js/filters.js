// Checks and chips stay on the page while a menu is open. The view updates
// when that menu closes, or when a click lands outside the filter bar.
// Without this script, Apply submits the form and a chip link drops that chip.
(() => {
  const form = document.querySelector(".keel-filters");
  if (!form) {
    return;
  }

  let dirty = false;
  let submitting = false;

  const commit = () => {
    if (!dirty || submitting) {
      return;
    }
    submitting = true;
    form.submit();
  };

  const caption = (box) => {
    const label = box.closest("label");
    return (label ? label.textContent : "").replace(/\s+/g, " ").trim();
  };

  const summarize = (menu) => {
    const value = menu.querySelector(".keel-multi__value");
    const boxes = [...menu.querySelectorAll("input[type='checkbox']")];
    if (!value || !boxes.length) {
      return;
    }
    const chosen = boxes.filter((box) => box.checked);
    if (chosen.length === boxes.length) {
      value.textContent = "All";
      return;
    }
    if (!chosen.length) {
      const name = menu
        .closest(".keel-filters__field")
        ?.querySelector(".keel-filters__name");
      value.textContent = name && name.textContent.trim() === "Type" ? "None" : "Any";
      return;
    }
    value.textContent = chosen.map(caption).join(", ");
  };

  const closeMenus = (target) => {
    for (const menu of form.querySelectorAll("details.keel-multi[open]")) {
      if (!menu.contains(target)) {
        menu.open = false;
      }
    }
  };

  form.addEventListener("toggle", (event) => {
    const menu = event.target;
    if (!(menu instanceof HTMLDetailsElement) || menu.open) {
      return;
    }
    commit();
  }, true);

  form.addEventListener("change", (event) => {
    const menu = event.target.closest(".keel-multi");
    if (menu) {
      dirty = true;
      summarize(menu);
      return;
    }
    if (event.target.name === "by") {
      dirty = true;
      commit();
    }
  });

  const chipsOf = (field) => {
    let wrap = field.querySelector(".keel-filters__chips");
    if (!wrap) {
      wrap = document.createElement("span");
      wrap.className = "keel-filters__chips";
      field.append(wrap);
    }
    return wrap;
  };

  form.addEventListener("keel-lookup-pick", (event) => {
    const box = event.target.closest("[data-keel-lookup-chip]");
    const field = box && box.closest(".keel-filters__field");
    const param = box && box.dataset.keelLookupChip;
    const label = event.detail && event.detail.label;
    if (!field || !param || !label) {
      return;
    }
    event.preventDefault();
    const wrap = chipsOf(field);
    const already = [...wrap.querySelectorAll("input")].some(
      (input) => input.name === param && input.value === label,
    );
    if (already) {
      return;
    }
    dirty = true;
    const chip = document.createElement("span");
    chip.className = "keel-chip keel-filters__chip";
    chip.append(document.createTextNode(label));
    const remove = document.createElement("a");
    remove.className = "keel-filters__remove";
    remove.href = "#";
    remove.setAttribute("aria-label", `Remove ${label}`);
    remove.textContent = "\u00d7";
    chip.append(remove);
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = param;
    hidden.value = label;
    wrap.append(chip, hidden);
  });

  form.addEventListener("click", (event) => {
    const link = event.target.closest(".keel-filters__remove");
    if (!link || !form.contains(link)) {
      return;
    }
    event.preventDefault();
    const chip = link.closest(".keel-filters__chip");
    if (!chip) {
      return;
    }
    dirty = true;
    const hidden = chip.nextElementSibling;
    if (hidden && hidden.matches("input[type='hidden']")) {
      hidden.remove();
    }
    const wrap = chip.parentElement;
    chip.remove();
    if (wrap && wrap.classList.contains("keel-filters__chips") && !wrap.children.length) {
      wrap.remove();
    }
  });

  document.addEventListener("pointerdown", (event) => {
    const target = event.target;
    if (!(target instanceof Node)) {
      return;
    }
    if (target.closest(".keel-filters__reset")) {
      return;
    }
    const choosing =
      target.closest("details.keel-multi[open]") ||
      target.closest(".keel-lookup") ||
      target.closest(".keel-filters__chips");
    if (choosing) {
      closeMenus(target);
      return;
    }
    const pending = dirty;
    closeMenus(target);
    if (pending) {
      event.preventDefault();
      commit();
    }
  });
})();
