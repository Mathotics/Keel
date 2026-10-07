// Suggests issues, labels, people, or projects for [data-keel-lookup] fields. A non-empty
// value has to be picked from the list before it can be submitted. An empty
// box is a clear. Fields marked data-keel-lookup-submit save on pick or clear,
// and their change events do not also trip the autosubmit listener.
// The suggestion list is a span so it stays inside the field. A ul there is
// pulled out of a paragraph, and this script then never sees it.
// Assign to me fills the people box with the signed-in person. On a field that
// saves on pick, that fill saves immediately; otherwise the form waits.
(() => {
  const boxes = document.querySelectorAll("[data-keel-lookup]");
  if (!boxes.length) {
    return;
  }

  const separator = " \u2014 ";

  const close = (input, list) => {
    list.hidden = true;
    list.replaceChildren();
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };

  const open = (input, list) => {
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  };

  for (const box of boxes) {
    const input = box.querySelector("input");
    const list = box.querySelector("[role='listbox']");
    if (!input || !list || !input.form) {
      continue;
    }
    const kind = box.dataset.keelLookup;
    const project = box.dataset.keelLookupProject || "";
    const exclude = box.dataset.keelLookupExclude || "";
    const idName = box.dataset.keelLookupId || "";
    const submitOnPick = box.hasAttribute("data-keel-lookup-submit");
    const emptyKind = box.dataset.keelLookupEmpty || "";
    const form = input.form;
    let committed = input.value;
    let hidden = null;
    let rows = [];
    let active = -1;
    let timer = 0;
    let controller = null;

    const clearHidden = () => {
      if (hidden) {
        hidden.remove();
        hidden = null;
      }
    };

    const ensureHidden = (id) => {
      if (!idName) {
        return;
      }
      if (!hidden) {
        hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = idName;
        box.append(hidden);
      }
      hidden.value = String(id);
    };

    const message = () => {
      if (kind === "labels") {
        return "Pick a label from the list.";
      }
      if (kind === "users") {
        return "Pick a person from the list.";
      }
      if (kind === "projects") {
        return "Pick a project from the list.";
      }
      return "Pick an issue from the list.";
    };

    const blocked = () => {
      if (!input.value.trim()) {
        return false;
      }
      return input.dataset.keelLookupDirty === "on";
    };

    const mark = () => {
      if (input.value === committed) {
        delete input.dataset.keelLookupDirty;
      } else {
        input.dataset.keelLookupDirty = "on";
        clearHidden();
      }
      input.setCustomValidity("");
    };

    const pick = (row) => {
      input.value = row.label;
      committed = row.label;
      delete input.dataset.keelLookupDirty;
      input.setCustomValidity("");
      if (row.id == null) {
        clearHidden();
      } else {
        ensureHidden(row.id);
      }
      close(input, list);
      const picked = new CustomEvent("keel-lookup-pick", {
        bubbles: true,
        cancelable: true,
        detail: row,
      });
      box.dispatchEvent(picked);
      if (picked.defaultPrevented) {
        input.value = "";
        committed = "";
        clearHidden();
        return;
      }
      if (submitOnPick) {
        form.submit();
      }
    };

    const assignMe = form.querySelector("[data-keel-assign-me]");
    if (kind === "users" && assignMe && !assignMe.dataset.keelAssignBound) {
      assignMe.dataset.keelAssignBound = "on";
      assignMe.addEventListener("click", (event) => {
        const id = assignMe.dataset.keelAssignMe;
        const label = assignMe.dataset.keelAssignMeLabel || "";
        if (!id) {
          return;
        }
        event.preventDefault();
        pick({ id: Number(id), label });
      });
    }

    const render = (items) => {
      rows = items;
      active = -1;
      list.replaceChildren();
      if (!items.length) {
        if ((kind === "issues" || kind === "projects") && !input.value.trim()) {
          close(input, list);
          return;
        }
        const empty = document.createElement("span");
        empty.className = "keel-lookup__empty";
        empty.textContent = "No matches";
        list.append(empty);
        open(input, list);
        return;
      }
      items.forEach((item, index) => {
        const option = document.createElement("span");
        option.className = "keel-lookup__option";
        option.setAttribute("role", "option");
        option.id = `${input.id}-opt-${index}`;
        option.textContent = item.label;
        option.addEventListener("mousedown", (event) => {
          event.preventDefault();
          pick(item);
        });
        list.append(option);
      });
      open(input, list);
    };

    const highlight = () => {
      const options = list.querySelectorAll("[role='option']");
      options.forEach((option, index) => {
        const selected = index === active;
        option.setAttribute("aria-selected", selected ? "true" : "false");
        if (selected) {
          input.setAttribute("aria-activedescendant", option.id);
          option.scrollIntoView({ block: "nearest" });
        }
      });
      if (active < 0) {
        input.removeAttribute("aria-activedescendant");
      }
    };

    const run = async () => {
      const q = input.value.trim();
      if ((kind === "issues" || kind === "projects") && !q) {
        close(input, list);
        return;
      }
      if (controller) {
        controller.abort();
      }
      controller = new AbortController();
      const params = new URLSearchParams();
      params.set("q", q);
      if (project) {
        params.set("project", project);
      }
      if (exclude) {
        params.set("exclude", exclude);
      }
      if (emptyKind) {
        params.set("empty", emptyKind);
      }
      const path =
        kind === "labels"
          ? "/web/lookup/labels"
          : kind === "users"
            ? "/web/lookup/users"
            : kind === "projects"
              ? "/web/lookup/projects"
              : "/web/lookup/issues";
      try {
        const response = await fetch(`${path}?${params.toString()}`, {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) {
          close(input, list);
          return;
        }
        const payload = await response.json();
        if (kind === "labels") {
          render(payload.map((name) => ({ label: name, id: null })));
        } else if (kind === "users") {
          render(payload.map((row) => ({ label: row.label, id: row.id })));
        } else if (kind === "projects") {
          render(
            payload.map((row) => ({
              label: `${row.key}${separator}${row.name}`,
              id: null,
            })),
          );
        } else {
          render(
            payload.map((row) => ({
              label: `${row.key}${separator}${row.title}`,
              id: row.id,
            })),
          );
        }
      } catch (error) {
        if (error.name !== "AbortError") {
          close(input, list);
        }
      }
    };

    const schedule = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(run, 150);
    };

    input.addEventListener("input", () => {
      mark();
      if (submitOnPick && !input.value.trim() && committed !== "") {
        committed = "";
        delete input.dataset.keelLookupDirty;
        clearHidden();
        close(input, list);
        form.submit();
        return;
      }
      schedule();
    });

    input.addEventListener("focus", () => {
      if (kind === "labels" || kind === "users" || input.value.trim()) {
        schedule();
      }
    });

    input.addEventListener("blur", () => {
      window.setTimeout(() => close(input, list), 150);
    });

    input.addEventListener(
      "change",
      (event) => {
        if (submitOnPick) {
          event.stopPropagation();
        }
      },
      true,
    );

    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (list.hidden) {
          schedule();
          return;
        }
        active = Math.min(active + 1, rows.length - 1);
        highlight();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        active = Math.max(active - 1, 0);
        highlight();
      } else if (event.key === "Enter" && !list.hidden && active >= 0) {
        event.preventDefault();
        pick(rows[active]);
      } else if (event.key === "Escape") {
        close(input, list);
      }
    });

    form.addEventListener(
      "submit",
      (event) => {
        if (!blocked()) {
          input.setCustomValidity("");
          return;
        }
        event.preventDefault();
        input.setCustomValidity(message());
        input.reportValidity();
      },
      true,
    );
  }
})();
