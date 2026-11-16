// Write / Preview for the Markdown fields. Write keeps the source. Preview
// shows that source rendered and still accepts edits, which are written back
// into the source. The toolbar toggles the same syntax the server renders,
// and a button stays highlighted while the caret is in that formatting.
// Without this script the textarea and the "Markdown is supported" note stay,
// and the bar stays hidden.
(() => {
  const editors = document.querySelectorAll("[data-keel-markdown]");
  if (!editors.length) {
    return;
  }
  document.documentElement.setAttribute("data-keel-md", "on");
  for (const editor of editors) {
    bindEditor(editor);
  }
  document.addEventListener("selectionchange", () => {
    for (const editor of editors) {
      refreshState(editor);
    }
  });

  function bindEditor(editor) {
    const textarea = editor.querySelector("textarea");
    const preview = editor.querySelector(".keel-md__preview");
    const writeTab = editor.querySelector("[data-keel-md-tab='write']");
    const previewTab = editor.querySelector("[data-keel-md-tab='preview']");
    if (!textarea || !preview || !writeTab || !previewTab) {
      return;
    }
    const label = textarea.id && document.querySelector(`label[for="${CSS.escape(textarea.id)}"]`);
    preview.setAttribute("role", "textbox");
    preview.setAttribute("aria-multiline", "true");
    if (label) {
      preview.setAttribute("aria-label", label.textContent.trim());
    }
    if (textarea.getAttribute("placeholder")) {
      preview.dataset.placeholder = textarea.getAttribute("placeholder");
    }
    const bar = editor.querySelector(".keel-md__bar");
    if (bar) {
      bar.addEventListener("mousedown", (event) => {
        event.preventDefault();
      });
    }
    const form = editor.closest("form");
    if (form && editor.querySelector(".keel-md__save")) {
      form.addEventListener("submit", () => {
        if (editor.classList.contains("is-preview")) {
          syncPreview(textarea, preview);
        }
      });
      form.addEventListener("reset", () => {
        window.setTimeout(() => {
          if (editor.classList.contains("is-preview")) {
            showPreview(editor, textarea, preview);
          }
        }, 0);
      });
      textarea.addEventListener("invalid", () => showWrite(editor, textarea));
    }
    writeTab.addEventListener("click", () => showWrite(editor, textarea));
    previewTab.addEventListener("click", () => showPreview(editor, textarea, preview));
    preview.addEventListener("input", () => {
      syncPreview(textarea, preview);
      refreshState(editor);
    });
    preview.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.shiftKey) {
        return;
      }
      const selection = window.getSelection();
      const node = selection && selection.anchorNode;
      if (closestTag(node, "li,pre")) {
        return;
      }
      event.preventDefault();
      document.execCommand("insertLineBreak");
    });
    preview.addEventListener("click", (event) => {
      const anchor = event.target.closest && event.target.closest("a");
      if (anchor && preview.contains(anchor)) {
        event.preventDefault();
      }
    });
    for (const button of editor.querySelectorAll("[data-keel-md]")) {
      button.addEventListener("click", () => {
        const action = button.getAttribute("data-keel-md");
        if (editor.classList.contains("is-preview")) {
          applyPreview(preview, action);
          syncPreview(textarea, preview);
          preview.focus();
        } else {
          applyWrite(textarea, action);
          textarea.focus();
        }
        refreshState(editor);
      });
    }
    refreshState(editor);
  }

  function showWrite(editor, textarea) {
    editor.classList.remove("is-preview");
    const preview = editor.querySelector(".keel-md__preview");
    if (preview) {
      preview.hidden = true;
      preview.contentEditable = "false";
    }
    markTabs(editor, "write");
    textarea.focus();
    refreshState(editor);
  }

  function showPreview(editor, textarea, preview) {
    editor.dataset.keelMdHold = "on";
    editor.classList.add("is-preview");
    markTabs(editor, "preview");
    preview.hidden = false;
    preview.contentEditable = "true";
    preview.classList.remove("is-blank");
    preview.textContent = "Preview…";
    const body = new FormData();
    body.set("body", textarea.value);
    fetch("/web/markdown/preview", { method: "POST", body, credentials: "same-origin" })
      .then((response) => {
        if (!response.ok || response.headers.get("X-Keel-Markdown") !== "preview") {
          preview.textContent = "Preview is unavailable.";
          preview.contentEditable = "false";
          return null;
        }
        return response.text();
      })
      .then((html) => {
        if (html === null || !editor.classList.contains("is-preview")) {
          return;
        }
        if (!textarea.value.trim()) {
          preview.innerHTML = "";
        } else {
          preview.innerHTML = html;
        }
        markBlank(preview);
        preview.focus();
      })
      .catch(() => {
        preview.textContent = "Preview is unavailable.";
        preview.contentEditable = "false";
      })
      .finally(() => {
        editor.dataset.keelMdHold = "";
        refreshState(editor);
      });
  }

  function markTabs(editor, mode) {
    for (const tab of editor.querySelectorAll("[data-keel-md-tab]")) {
      const selected = tab.getAttribute("data-keel-md-tab") === mode;
      tab.classList.toggle("is-selected", selected);
      tab.setAttribute("aria-selected", selected ? "true" : "false");
    }
  }

  function refreshState(editor) {
    const textarea = editor.querySelector("textarea");
    const state = editor.classList.contains("is-preview") ? previewState(editor) : writeState(textarea);
    for (const button of editor.querySelectorAll("[data-keel-md]")) {
      const on = !!state[button.getAttribute("data-keel-md")];
      button.setAttribute("aria-pressed", on ? "true" : "false");
    }
  }

  function writeState(textarea) {
    if (!textarea) {
      return {};
    }
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const value = textarea.value;
    const lines = lineBlock(value, start, end).lines;
    if (document.activeElement !== textarea) {
      return {};
    }
    const emphasis = emphasisAt(value, start, end);
    return {
      heading: lines.length > 0 && lines.every((line) => lineKind(line) === "heading"),
      bold: !!emphasis.bold,
      italic: !!emphasis.italic,
      quote: lines.length > 0 && lines.every((line) => lineKind(line) === "quote"),
      code: !!fenceAround(value, start, end) || !!emphasis.code,
      link: !!linkAround(value, start, end),
      bullet: lines.length > 0 && lines.every((line) => lineKind(line) === "bullet"),
      number: lines.length > 0 && lines.every((line) => lineKind(line) === "number"),
    };
  }

  function previewState(editor) {
    const preview = editor.querySelector(".keel-md__preview");
    const selection = window.getSelection();
    if (!preview || !selection || !selection.anchorNode || !preview.contains(selection.anchorNode)) {
      return {};
    }
    const node = selection.anchorNode;
    return {
      heading: !!closestTag(node, "h1,h2,h3,h4,h5,h6"),
      bold: !!closestTag(node, "strong, b"),
      italic: !!closestTag(node, "em, i"),
      quote: !!closestTag(node, "blockquote"),
      code: !!closestTag(node, "code,pre"),
      link: !!closestTag(node, "a"),
      bullet: !!closestTag(node, "ul"),
      number: !!closestTag(node, "ol"),
    };
  }

  function applyWrite(textarea, action) {
    if (action === "bold") {
      toggleInline(textarea, "**");
    } else if (action === "italic") {
      toggleInline(textarea, "*");
    } else if (action === "code") {
      toggleCode(textarea);
    } else if (action === "link") {
      toggleLink(textarea);
    } else if (action === "heading" || action === "quote" || action === "bullet" || action === "number") {
      togglePrefix(textarea, action);
    }
  }

  function applyPreview(preview, action) {
    preview.focus();
    const selection = window.getSelection();
    const node = selection && selection.anchorNode;
    document.execCommand("styleWithCSS", false, false);
    if (action === "bold") {
      togglePreviewMark("bold", "strong, b", "strong");
    } else if (action === "italic") {
      togglePreviewMark("italic", "em, i", "em");
    } else if (action === "bullet") {
      document.execCommand("insertUnorderedList");
    } else if (action === "number") {
      document.execCommand("insertOrderedList");
    } else if (action === "heading") {
      if (closestTag(node, "h1,h2,h3,h4,h5,h6")) {
        document.execCommand("formatBlock", false, "p");
      } else {
        document.execCommand("formatBlock", false, "h2");
      }
    } else if (action === "quote") {
      const quote = closestTag(node, "blockquote");
      if (quote) {
        unwrap(quote);
      } else {
        document.execCommand("formatBlock", false, "blockquote");
      }
    } else if (action === "code") {
      togglePreviewCode(preview);
    } else if (action === "link") {
      togglePreviewLink();
    }
    markBlank(preview);
  }

  // Bold and italic follow the tags the markdown source can store. A heading's
  // own weight is not bold: the browser would report it as bold and a click
  // would only change a style the source cannot keep.
  function togglePreviewMark(command, selector, tag) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return;
    }
    const existing = selectedMark(selection, selector);
    if (existing || !document.queryCommandState(command)) {
      document.execCommand(command);
      return;
    }
    if (selection.isCollapsed) {
      const mark = document.createElement(tag);
      const range = selection.getRangeAt(0);
      range.insertNode(mark);
      range.selectNodeContents(mark);
      range.collapse(false);
      selection.removeAllRanges();
      selection.addRange(range);
      return;
    }
    document.execCommand("insertHTML", false, "<" + tag + ">" + escapeHtml(selection.toString()) + "</" + tag + ">");
  }

  function selectedMark(selection, selector) {
    const direct = closestTag(selection.anchorNode, selector);
    if (direct) {
      return direct;
    }
    if (selection.isCollapsed) {
      return null;
    }
    const range = selection.getRangeAt(0);
    const root = range.commonAncestorContainer;
    const scope = root.nodeType === Node.ELEMENT_NODE ? root : root.parentElement;
    if (!scope) {
      return null;
    }
    return [...scope.querySelectorAll(selector)].find((mark) => range.intersectsNode(mark)) || null;
  }

  function togglePrefix(textarea, kind) {
    const value = textarea.value;
    const block = lineBlock(value, textarea.selectionStart, textarea.selectionEnd);
    const active = block.lines.length > 0 && block.lines.every((line) => lineKind(line) === kind);
    const next = block.lines
      .map((line, index) => {
        const text = stripKind(line);
        if (active) {
          return text;
        }
        if (kind === "bullet") {
          return "- " + text;
        }
        if (kind === "number") {
          return String(index + 1) + ". " + text;
        }
        if (kind === "quote") {
          return "> " + text;
        }
        return "## " + text;
      })
      .join("\n");
    replace(textarea, block.start, block.end, next);
    textarea.setSelectionRange(block.start, block.start + next.length);
  }

  function lineBlock(value, start, end) {
    let to = end;
    if (to > start && value.charAt(to - 1) === "\n") {
      to -= 1;
    }
    const startAt = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    let endAt = value.indexOf("\n", to);
    if (endAt < 0) {
      endAt = value.length;
    }
    return { start: startAt, end: endAt, lines: value.slice(startAt, endAt).split("\n") };
  }

  function lineKind(line) {
    if (/^\d+\. /.test(line)) {
      return "number";
    }
    if (line.startsWith("- ")) {
      return "bullet";
    }
    if (line.startsWith("> ")) {
      return "quote";
    }
    if (line.startsWith("## ")) {
      return "heading";
    }
    return "";
  }

  function stripKind(line) {
    if (/^\d+\. /.test(line)) {
      return line.replace(/^\d+\. /, "");
    }
    if (line.startsWith("- ") || line.startsWith("> ")) {
      return line.slice(2);
    }
    if (line.startsWith("## ")) {
      return line.slice(3);
    }
    return line;
  }

  function toggleInline(textarea, mark) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const emphasis = emphasisAt(textarea.value, start, end);
    const span = mark === "**" ? emphasis.bold : mark === "`" ? emphasis.code : emphasis.italic;
    if (span && start >= span.innerStart && end <= span.innerEnd) {
      unapplyInline(textarea, span, mark);
      return;
    }
    const selected = textarea.value.slice(start, end);
    if (selected.startsWith(mark) && selected.endsWith(mark) && selected.length >= mark.length * 2) {
      const inner = selected.slice(mark.length, selected.length - mark.length);
      replace(textarea, start, end, inner);
      textarea.setSelectionRange(start, start + inner.length);
      return;
    }
    replace(textarea, start, end, mark + selected + mark);
    textarea.setSelectionRange(start + mark.length, end + mark.length);
  }

  function unapplyInline(textarea, span, mark) {
    const value = textarea.value;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const inner = value.slice(span.innerStart, span.innerEnd);
    if (start === end || (start <= span.innerStart && end >= span.innerEnd)) {
      replace(textarea, span.open, span.close, inner);
      const caret = start === end ? Math.max(span.innerStart, start) - mark.length : span.open;
      const caretEnd = start === end ? caret : span.open + inner.length;
      textarea.setSelectionRange(caret, caretEnd);
      return;
    }
    const before = value.slice(span.innerStart, start);
    const selected = value.slice(start, end);
    const after = value.slice(end, span.innerEnd);
    let next = "";
    if (before) {
      next += mark + before + mark;
    }
    next += selected;
    if (after) {
      next += mark + after + mark;
    }
    replace(textarea, span.open, span.close, next);
    const newStart = span.open + (before ? before.length + mark.length * 2 : 0);
    textarea.setSelectionRange(newStart, newStart + selected.length);
  }

  function toggleCode(textarea) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const fence = fenceAround(textarea.value, start, end);
    if (fence) {
      const value = textarea.value;
      let innerStart = value.indexOf("\n", fence.open);
      innerStart = innerStart < 0 ? fence.open + 3 : innerStart + 1;
      let innerEnd = value.lastIndexOf("\n", fence.close - 1);
      if (innerEnd < fence.open) {
        innerEnd = fence.close - 3;
      }
      const inner = value.slice(innerStart, innerEnd).replace(/\n$/, "");
      replace(textarea, fence.open, fence.close, inner);
      textarea.setSelectionRange(fence.open, fence.open + inner.length);
      return;
    }
    const span = emphasisAt(textarea.value, start, end).code;
    if (span && start >= span.innerStart && end <= span.innerEnd) {
      unapplyInline(textarea, span, "`");
      return;
    }
    const selected = textarea.value.slice(start, end);
    if (selected.indexOf("\n") !== -1) {
      const fenced = "```\n" + selected + "\n```";
      replace(textarea, start, end, fenced);
      textarea.setSelectionRange(start + 4, start + 4 + selected.length);
      return;
    }
    toggleInline(textarea, "`");
  }

  function toggleLink(textarea) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const link = linkAround(textarea.value, start, end);
    if (link) {
      replace(textarea, link.open, link.close, link.text);
      textarea.setSelectionRange(link.open, link.open + link.text.length);
      return;
    }
    const selected = textarea.value.slice(start, end) || "text";
    replace(textarea, start, end, "[" + selected + "](url)");
    const urlAt = start + selected.length + 3;
    textarea.setSelectionRange(urlAt, urlAt + 3);
  }

  function emphasisAt(value, start, end) {
    const fence = fenceAround(value, start, end);
    const empty = { bold: null, italic: null, code: null };
    if (fence) {
      return empty;
    }
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    let lineEnd = value.indexOf("\n", end);
    if (lineEnd < 0) {
      lineEnd = value.length;
    }
    const line = value.slice(lineStart, lineEnd);
    const relStart = start - lineStart;
    const relEnd = end - lineStart;
    const spans = { bold: [], italic: [], code: [] };
    let boldFrom = -1;
    let italicFrom = -1;
    let codeFrom = -1;
    let index = 0;
    while (index < line.length) {
      if (codeFrom >= 0) {
        if (line.charAt(index) === "`") {
          spans.code.push(span(lineStart, codeFrom, index, 1));
          codeFrom = -1;
        }
        index += 1;
        continue;
      }
      if (line.charAt(index) === "`") {
        codeFrom = index;
        index += 1;
        continue;
      }
      if (line.startsWith("**", index)) {
        if (boldFrom >= 0) {
          spans.bold.push(span(lineStart, boldFrom, index, 2));
          boldFrom = -1;
        } else {
          boldFrom = index;
        }
        index += 2;
        continue;
      }
      if (line.charAt(index) === "*" && line.charAt(index - 1) !== "*") {
        if (italicFrom >= 0) {
          spans.italic.push(span(lineStart, italicFrom, index, 1));
          italicFrom = -1;
        } else {
          italicFrom = index;
        }
        index += 1;
        continue;
      }
      index += 1;
    }
    return {
      bold: covering(spans.bold, relStart, relEnd, lineStart),
      italic: covering(spans.italic, relStart, relEnd, lineStart),
      code: covering(spans.code, relStart, relEnd, lineStart),
    };
  }

  function span(lineStart, open, close, markLength) {
    return {
      open: lineStart + open,
      close: lineStart + close + markLength,
      innerStart: lineStart + open + markLength,
      innerEnd: lineStart + close,
    };
  }

  function covering(spans, relStart, relEnd, lineStart) {
    return (
      spans.find((item) => {
        const start = relStart + lineStart;
        const end = relEnd + lineStart;
        if (start === end) {
          return start >= item.innerStart && start <= item.innerEnd;
        }
        const inside = start >= item.innerStart && end <= item.innerEnd;
        const around = start <= item.open && end >= item.close;
        return inside || around;
      }) || null
    );
  }

  function linkAround(value, start, end) {
    const lineStart = value.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
    let lineEnd = value.indexOf("\n", end);
    if (lineEnd < 0) {
      lineEnd = value.length;
    }
    const line = value.slice(lineStart, lineEnd);
    const pattern = /\[([^\[\]]*)\]\(([^)]*)\)/g;
    let match = pattern.exec(line);
    while (match) {
      const open = lineStart + match.index;
      const close = open + match[0].length;
      const caret = start === end && start >= open && start <= close;
      const selected = start !== end && start >= open && end <= close;
      if (caret || selected) {
        return { open, close, text: match[1] };
      }
      match = pattern.exec(line);
    }
    return null;
  }

  function fenceAround(value, start, end) {
    let open = -1;
    for (let index = 0; index <= value.length - 3; index += 1) {
      if (!value.startsWith("```", index)) {
        continue;
      }
      if (open < 0) {
        open = index;
      } else {
        const close = index + 3;
        if (start >= open && end <= close) {
          return { open, close };
        }
        open = -1;
      }
      index += 2;
    }
    return null;
  }

  function togglePreviewCode(preview) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return;
    }
    const code = closestTag(selection.anchorNode, "code");
    const pre = closestTag(selection.anchorNode, "pre");
    if (code && (!pre || code.parentElement !== pre)) {
      unwrap(code);
      return;
    }
    if (pre) {
      const text = document.createTextNode(pre.textContent.replace(/\n$/, ""));
      pre.replaceWith(text);
      return;
    }
    const text = selection.toString();
    if (text.indexOf("\n") !== -1) {
      document.execCommand("insertHTML", false, "<pre><code>" + escapeHtml(text) + "</code></pre>");
      return;
    }
    document.execCommand("insertHTML", false, "<code>" + escapeHtml(text) + "</code>");
  }

  function togglePreviewLink() {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return;
    }
    const anchor = closestTag(selection.anchorNode, "a");
    if (anchor) {
      unwrap(anchor);
      return;
    }
    const text = selection.toString() || "text";
    document.execCommand("insertHTML", false, '<a href="url">' + escapeHtml(text) + "</a>");
  }

  function syncPreview(textarea, preview) {
    if (preview.querySelector(".keel-empty") && !preview.textContent.replace("Nothing to preview.", "").trim()) {
      textarea.value = "";
      markBlank(preview);
      return;
    }
    textarea.value = htmlToMarkdown(preview);
    markBlank(preview);
  }

  function markBlank(preview) {
    preview.classList.toggle("is-blank", !preview.textContent.trim());
  }

  function htmlToMarkdown(root) {
    const parts = [];
    for (const node of root.childNodes) {
      const block = blockToMarkdown(node);
      if (block) {
        parts.push(block);
      }
    }
    return parts.join("\n\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function blockToMarkdown(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent.replace(/\u00a0/g, " ").trim();
      return text || null;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }
    const tag = node.tagName;
    if (tag === "SCRIPT" || tag === "STYLE") {
      return null;
    }
    if (node.classList && node.classList.contains("keel-empty")) {
      return null;
    }
    if (tag === "P" || tag === "DIV") {
      if (hasBlock(node)) {
        return htmlToMarkdown(node);
      }
      const text = inlineMarkdown(node).replace(/[ \t]+\n/g, "\n").trim();
      return text || null;
    }
    if (/^H[1-6]$/.test(tag)) {
      return "#".repeat(Number(tag.charAt(1))) + " " + inlineMarkdown(node).trim();
    }
    if (tag === "BLOCKQUOTE") {
      const inner = htmlToMarkdown(node);
      if (!inner) {
        return null;
      }
      return inner
        .split("\n")
        .map((line) => "> " + line)
        .join("\n");
    }
    if (tag === "UL") {
      return [...node.children]
        .filter((child) => child.tagName === "LI")
        .map((item) => "- " + itemMarkdown(item))
        .join("\n");
    }
    if (tag === "OL") {
      return [...node.children]
        .filter((child) => child.tagName === "LI")
        .map((item, index) => String(index + 1) + ". " + itemMarkdown(item))
        .join("\n");
    }
    if (tag === "PRE") {
      const code = node.querySelector("code");
      const text = (code || node).textContent.replace(/\n$/, "");
      return "```\n" + text + "\n```";
    }
    if (tag === "HR") {
      return "---";
    }
    if (tag === "TABLE") {
      return tableToMarkdown(node);
    }
    return inlineMarkdown(node).trim() || null;
  }

  function itemMarkdown(item) {
    if (hasBlock(item)) {
      return htmlToMarkdown(item).replace(/\n/g, "\n  ");
    }
    return inlineMarkdown(item).trim();
  }

  function hasBlock(node) {
    return !!node.querySelector("p,div,ul,ol,blockquote,pre,table,h1,h2,h3,h4,h5,h6");
  }

  function inlineMarkdown(node) {
    let text = "";
    for (const child of node.childNodes) {
      text += inlineNode(child);
    }
    return text.replace(/\u00a0/g, " ");
  }

  function inlineNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      return node.textContent;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return "";
    }
    const tag = node.tagName;
    if (tag === "BR") {
      return "\n";
    }
    if (tag === "STRONG" || tag === "B") {
      return "**" + inlineMarkdown(node) + "**";
    }
    if (tag === "EM" || tag === "I") {
      return "*" + inlineMarkdown(node) + "*";
    }
    if (tag === "CODE") {
      return "`" + node.textContent + "`";
    }
    if (tag === "A") {
      return "[" + inlineMarkdown(node) + "](" + (node.getAttribute("href") || "") + ")";
    }
    if (tag === "UL" || tag === "OL" || tag === "PRE" || tag === "BLOCKQUOTE" || tag === "TABLE") {
      return blockToMarkdown(node) || "";
    }
    return inlineMarkdown(node);
  }

  function tableToMarkdown(table) {
    const rows = [...table.querySelectorAll("tr")];
    if (!rows.length) {
      return null;
    }
    const cells = (row) =>
      [...row.children].map((cell) => inlineMarkdown(cell).replace(/\|/g, "\\|").replace(/\n/g, " ").trim());
    const header = cells(rows[0]);
    const lines = [
      "| " + header.join(" | ") + " |",
      "| " + header.map(() => "---").join(" | ") + " |",
    ];
    for (const row of rows.slice(1)) {
      lines.push("| " + cells(row).join(" | ") + " |");
    }
    return lines.join("\n");
  }

  function closestTag(node, selector) {
    const element = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
    return element && element.closest(selector);
  }

  function unwrap(element) {
    const parent = element.parentNode;
    while (element.firstChild) {
      parent.insertBefore(element.firstChild, element);
    }
    parent.removeChild(element);
  }

  function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function replace(textarea, start, end, text) {
    textarea.setRangeText(text, start, end, "end");
  }
})();
