// Write / Preview for the Markdown fields. The toolbar inserts the same
// source the server already renders. Preview asks the server, so the tab
// cannot drift from the saved note. Without this script the textarea and the
// "Markdown is supported" note stay, and the bar stays hidden.
(() => {
  const editors = document.querySelectorAll("[data-keel-markdown]");
  if (!editors.length) {
    return;
  }
  document.documentElement.setAttribute("data-keel-md", "on");
  for (const editor of editors) {
    bindEditor(editor);
  }

  function bindEditor(editor) {
    const textarea = editor.querySelector("textarea");
    const preview = editor.querySelector(".keel-md__preview");
    const writeTab = editor.querySelector("[data-keel-md-tab='write']");
    const previewTab = editor.querySelector("[data-keel-md-tab='preview']");
    if (!textarea || !preview || !writeTab || !previewTab) {
      return;
    }
    const bar = editor.querySelector(".keel-md__bar");
    if (bar) {
      bar.addEventListener("mousedown", (event) => {
        event.preventDefault();
      });
    }
    textarea.addEventListener("change", (event) => {
      if (editor.dataset.keelMdHold === "on" || editor.contains(document.activeElement)) {
        event.stopPropagation();
      }
    });
    writeTab.addEventListener("click", () => showWrite(editor, textarea));
    previewTab.addEventListener("click", () => showPreview(editor, textarea, preview));
    for (const button of editor.querySelectorAll("[data-keel-md]")) {
      button.addEventListener("click", () => {
        if (editor.classList.contains("is-preview")) {
          return;
        }
        apply(textarea, button.getAttribute("data-keel-md"));
      });
    }
  }

  function showWrite(editor, textarea) {
    editor.classList.remove("is-preview");
    const preview = editor.querySelector(".keel-md__preview");
    if (preview) {
      preview.hidden = true;
    }
    markTabs(editor, "write");
    textarea.focus();
  }

  function showPreview(editor, textarea, preview) {
    editor.dataset.keelMdHold = "on";
    editor.classList.add("is-preview");
    markTabs(editor, "preview");
    preview.hidden = false;
    preview.textContent = "Preview…";
    const body = new FormData();
    body.set("body", textarea.value);
    fetch("/web/markdown/preview", { method: "POST", body, credentials: "same-origin" })
      .then((response) => {
        if (!response.ok || response.headers.get("X-Keel-Markdown") !== "preview") {
          preview.textContent = "Preview is unavailable.";
          return null;
        }
        return response.text();
      })
      .then((html) => {
        if (html !== null && editor.classList.contains("is-preview")) {
          preview.innerHTML = html;
        }
      })
      .catch(() => {
        preview.textContent = "Preview is unavailable.";
      })
      .finally(() => {
        editor.dataset.keelMdHold = "";
      });
  }

  function markTabs(editor, mode) {
    for (const tab of editor.querySelectorAll("[data-keel-md-tab]")) {
      const selected = tab.getAttribute("data-keel-md-tab") === mode;
      tab.classList.toggle("is-selected", selected);
      tab.setAttribute("aria-selected", selected ? "true" : "false");
    }
  }

  function apply(textarea, action) {
    if (action === "bold") {
      toggleWrap(textarea, "**");
    } else if (action === "italic") {
      toggleWrap(textarea, "*");
    } else if (action === "code") {
      insertCode(textarea);
    } else if (action === "link") {
      insertLink(textarea);
    } else if (action === "heading") {
      prefixLines(textarea, (line) => (line.startsWith("## ") ? line.slice(3) : "## " + line));
    } else if (action === "quote") {
      prefixLines(textarea, (line) => (line.startsWith("> ") ? line : "> " + line));
    } else if (action === "bullet") {
      prefixLines(textarea, (line) => (line.startsWith("- ") ? line : "- " + line));
    } else if (action === "number") {
      prefixLines(textarea, (line, index) => String(index + 1) + ". " + stripNumber(line));
    }
    textarea.focus();
  }

  function toggleWrap(textarea, mark) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const value = textarea.value;
    const selected = value.slice(start, end);
    if (value.slice(start - mark.length, start) === mark && value.slice(end, end + mark.length) === mark) {
      replace(textarea, start - mark.length, end + mark.length, selected);
      textarea.setSelectionRange(start - mark.length, end - mark.length);
      return;
    }
    if (selected.startsWith(mark) && selected.endsWith(mark) && selected.length >= mark.length * 2) {
      const inner = selected.slice(mark.length, selected.length - mark.length);
      replace(textarea, start, end, inner);
      textarea.setSelectionRange(start, start + inner.length);
      return;
    }
    replace(textarea, start, end, mark + selected + mark);
    const cursor = start + mark.length;
    textarea.setSelectionRange(cursor, cursor + selected.length);
  }

  function insertCode(textarea) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = textarea.value.slice(start, end);
    if (selected.indexOf("\n") !== -1) {
      const fenced = "```\n" + selected + "\n```";
      replace(textarea, start, end, fenced);
      textarea.setSelectionRange(start + 4, start + 4 + selected.length);
      return;
    }
    toggleWrap(textarea, "`");
  }

  function insertLink(textarea) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const selected = textarea.value.slice(start, end) || "text";
    replace(textarea, start, end, "[" + selected + "](url)");
    const urlAt = start + selected.length + 3;
    textarea.setSelectionRange(urlAt, urlAt + 3);
  }

  function prefixLines(textarea, format) {
    const value = textarea.value;
    let start = textarea.selectionStart;
    let end = textarea.selectionEnd;
    if (end > start && value.charAt(end - 1) === "\n") {
      end -= 1;
    }
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    let lineEnd = value.indexOf("\n", end);
    if (lineEnd < 0) {
      lineEnd = value.length;
    }
    const lines = value.slice(lineStart, lineEnd).split("\n");
    const next = lines.map((line, index) => format(line, index)).join("\n");
    replace(textarea, lineStart, lineEnd, next);
    textarea.setSelectionRange(lineStart, lineStart + next.length);
  }

  function stripNumber(line) {
    let index = 0;
    while (index < line.length && line.charCodeAt(index) >= 48 && line.charCodeAt(index) <= 57) {
      index += 1;
    }
    if (index > 0 && line.slice(index, index + 2) === ". ") {
      return line.slice(index + 2);
    }
    return line;
  }

  function replace(textarea, start, end, text) {
    textarea.setRangeText(text, start, end, "end");
  }
})();
