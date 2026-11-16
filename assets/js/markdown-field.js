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
    let caret = null;
    if (bar) {
      bar.addEventListener("mousedown", (event) => {
        event.preventDefault();
        caret = null;
        const selection = window.getSelection();
        if (document.activeElement === textarea) {
          caret = { kind: "write", start: textarea.selectionStart, end: textarea.selectionEnd };
        } else if (selection && selection.rangeCount && preview.contains(selection.anchorNode)) {
          caret = { kind: "preview", range: selection.getRangeAt(0).cloneRange() };
        }
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
          refreshSave(editor, textarea);
        }, 0);
      });
      textarea.addEventListener("invalid", () => showWrite(editor, textarea));
    }
    textarea.addEventListener("input", () => refreshSave(editor, textarea));
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
      if (!selection || !selection.isCollapsed || !node || !preview.contains(node)) {
        return;
      }
      const heading = closestTag(node, "h1,h2,h3,h4,h5,h6");
      if (heading && preview.contains(heading)) {
        event.preventDefault();
        splitAfterCaret(heading, "p");
        syncPreview(textarea, preview);
        refreshSave(editor, textarea);
        return;
      }
      const item = closestTag(node, "li");
      if (item && preview.contains(item)) {
        event.preventDefault();
        if (atBlockStart(item)) {
          liftListItem(item);
        } else {
          splitAfterCaret(item, "li");
        }
        syncPreview(textarea, preview);
        refreshSave(editor, textarea);
        return;
      }
      const quote = closestTag(node, "blockquote");
      if (quote && preview.contains(quote)) {
        event.preventDefault();
        enterInQuote(quote);
        syncPreview(textarea, preview);
        refreshSave(editor, textarea);
        return;
      }
      if (closestTag(node, "pre")) {
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
          const opened = applyPreview(preview, action, caret);
          syncPreview(textarea, preview);
          if (opened !== "dialog") {
            preview.focus();
          }
        } else {
          restoreCaret(caret, textarea);
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
    if (textarea) {
      refreshSave(editor, textarea);
    }
  }

  function refreshSave(editor, textarea) {
    const save = editor.querySelector(".keel-md__save");
    if (!save) {
      return;
    }
    save.disabled = textarea.value === textarea.defaultValue;
  }

  function writeState(textarea) {
    if (!textarea || document.activeElement !== textarea || !window.KeelMarkdownSource) {
      return {};
    }
    return window.KeelMarkdownSource.state(textarea.value, textarea.selectionStart, textarea.selectionEnd);
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
    if (!window.KeelMarkdownSource) {
      return;
    }
    const next = window.KeelMarkdownSource.edit(textarea.value, textarea.selectionStart, textarea.selectionEnd, action);
    textarea.value = next.value;
    textarea.setSelectionRange(next.start, next.end);
  }

  function applyPreview(preview, action, caret) {
    preview.focus();
    if (caret && caret.kind === "preview") {
      const saved = window.getSelection();
      saved.removeAllRanges();
      saved.addRange(caret.range);
    }
    const selection = window.getSelection();
    const node = selection && selection.anchorNode;
    document.execCommand("styleWithCSS", false, false);
    if (action === "bold") {
      togglePreviewMark("bold", "strong, b", "strong");
    } else if (action === "italic") {
      togglePreviewMark("italic", "em, i", "em");
    } else if (action === "bullet") {
      togglePreviewList(preview, false);
    } else if (action === "number") {
      togglePreviewList(preview, true);
    } else if (action === "heading") {
      const heading = closestTag(node, "h1,h2,h3,h4,h5,h6");
      if (heading && preview.contains(heading)) {
        replaceWithParagraph(heading);
      } else {
        document.execCommand("formatBlock", false, "h2");
      }
    } else if (action === "quote") {
      togglePreviewQuote(preview);
    } else if (action === "code") {
      togglePreviewCode(preview);
    } else if (action === "link") {
      const opened = togglePreviewLink(preview);
      markBlank(preview);
      return opened ? "dialog" : undefined;
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
    const range = selection.getRangeAt(0);
    const existing = selectedMark(selection, selector);
    if (selection.isCollapsed) {
      if (existing) {
        leaveMark(existing);
      } else {
        insertEmptyMark(tag);
      }
      return;
    }
    const marks = marksInRange(range, selector);
    const sole = marks.length === 1 && rangeInside(range, marks[0]) ? marks[0] : null;
    if (sole) {
      removeMarkFromRange(sole, range);
      return;
    }
    wrapRangeUnifying(range, tag, selector);
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

  function togglePreviewCode(preview) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return;
    }
    const code = closestTag(selection.anchorNode, "code");
    const pre = closestTag(selection.anchorNode, "pre");
    if (code && (!pre || code.parentElement !== pre)) {
      if (selection.isCollapsed) {
        unwrapKeepCaret(code);
      } else if (rangeInside(selection.getRangeAt(0), code)) {
        removeMarkFromRange(code, selection.getRangeAt(0));
      } else {
        unwrap(code);
      }
      return;
    }
    if (pre && preview.contains(pre)) {
      unwrapKeepCaret(pre);
      return;
    }
    if (selection.isCollapsed) {
      insertEmptyMark("code");
      return;
    }
    const text = selection.toString();
    if (text.indexOf("\n") !== -1) {
      document.execCommand("insertHTML", false, "<pre><code>" + escapeHtml(text) + "</code></pre>");
      return;
    }
    document.execCommand("insertHTML", false, "<code>" + escapeHtml(text) + "</code>");
  }

  function togglePreviewLink(preview) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount || !preview.contains(selection.anchorNode)) {
      return false;
    }
    const anchors = anchorsInSelection(preview, selection);
    if (anchors.length >= 2) {
      return false;
    }
    const anchor = anchors[0] || null;
    const range = selection.getRangeAt(0).cloneRange();
    const dialog = linkDialog();
    const text = dialog.querySelector("[name='text']");
    const href = dialog.querySelector("[name='link']");
    text.value = anchor ? anchor.textContent : selection.toString() || "text";
    href.value = anchor ? anchor.getAttribute("href") || "" : "url";
    dialog.returnValue = "";
    dialog.showModal();
    href.focus();
    href.select();
    dialog.addEventListener(
      "close",
      () => {
        if (dialog.returnValue === "remove") {
          if (anchor) {
            anchor.replaceWith(document.createTextNode(anchor.textContent));
          }
        } else if (dialog.returnValue === "ok") {
          if (anchor) {
            anchor.textContent = text.value;
            anchor.setAttribute("href", href.value);
          } else {
            const link = document.createElement("a");
            link.setAttribute("href", href.value);
            link.textContent = text.value;
            range.deleteContents();
            range.insertNode(link);
          }
        } else {
          return;
        }
        preview.dispatchEvent(new Event("input", { bubbles: true }));
        preview.focus();
      },
      { once: true },
    );
    return true;
  }

  function linkDialog() {
    let dialog = document.querySelector(".keel-md__link-dialog");
    if (dialog) {
      return dialog;
    }
    dialog = document.createElement("dialog");
    dialog.className = "keel-md__link-dialog";
    dialog.innerHTML =
      "<form method='dialog' class='keel-md__link-form'>" +
      "<label>Text <input name='text' type='text'></label>" +
      "<label>Link <input name='link' type='text'></label>" +
      "<span class='keel-md__link-actions'>" +
      "<button type='submit' value='ok'>OK</button>" +
      "<button type='button' value='remove'>Remove link</button>" +
      "<button type='submit' value='cancel'>Cancel</button>" +
      "</span></form>";
    dialog.querySelector("[value='remove']").addEventListener("click", () => {
      dialog.close("remove");
    });
    document.body.appendChild(dialog);
    return dialog;
  }

  function anchorsInSelection(preview, selection) {
    const range = selection.getRangeAt(0);
    const found = [];
    const direct = closestTag(selection.anchorNode, "a");
    if (direct && preview.contains(direct)) {
      found.push(direct);
    }
    const root = range.commonAncestorContainer;
    const scope = root.nodeType === Node.ELEMENT_NODE ? root : root.parentElement;
    if (!scope) {
      return found;
    }
    for (const anchor of scope.querySelectorAll("a")) {
      if (preview.contains(anchor) && range.intersectsNode(anchor) && !found.includes(anchor)) {
        found.push(anchor);
      }
    }
    return found;
  }

  function togglePreviewQuote(preview) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount || !selection.anchorNode || !preview.contains(selection.anchorNode)) {
      insertEmptyQuote(preview);
      return;
    }
    const blocks = blocksInRange(preview, selection);
    if (!blocks.length) {
      insertEmptyQuote(preview);
      return;
    }
    const quotes = [];
    const plain = [];
    for (const block of blocks) {
      const quote = block.tagName === "BLOCKQUOTE" ? block : closestTag(block, "blockquote");
      if (quote && preview.contains(quote)) {
        if (!quotes.includes(quote)) {
          quotes.push(quote);
        }
      } else {
        plain.push(block);
      }
    }
    if (quotes.length) {
      for (const quote of quotes) {
        unwrap(quote);
      }
      return;
    }
    for (const block of plain) {
      const quote = document.createElement("blockquote");
      block.replaceWith(quote);
      quote.appendChild(block);
    }
  }

  function insertEmptyQuote(preview) {
    const quote = document.createElement("blockquote");
    const paragraph = document.createElement("p");
    paragraph.appendChild(document.createElement("br"));
    quote.appendChild(paragraph);
    preview.appendChild(quote);
    const point = document.createRange();
    point.setStart(paragraph, 0);
    point.collapse(true);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(point);
  }

  function enterInQuote(quote) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount) {
      return;
    }
    const caret = selection.getRangeAt(0);
    const host = quoteHost(caret.startContainer, quote);
    if (host && emptyQuoteSegment(host, caret) && textBeforeQuoteSegment(quote, host, caret).trim()) {
      leaveEmptyQuoteLine(quote, host, caret);
      return;
    }
    if (atBlockStart(quote)) {
      unwrap(quote);
      return;
    }
    continueQuoteLine(host, caret);
  }

  function quoteHost(node, quote) {
    const element = node && (node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement);
    if (!element) {
      return null;
    }
    const paragraph = element.closest("p");
    if (paragraph && quote.contains(paragraph)) {
      return paragraph;
    }
    return quote.contains(element) ? quote : null;
  }

  function quoteSegments(host) {
    const segments = [];
    let start = 0;
    let seen = false;
    for (let index = 0; index < host.childNodes.length; index += 1) {
      const child = host.childNodes[index];
      if (child.nodeName === "BR") {
        if (seen) {
          segments.push({ start, end: index });
          start = index + 1;
          seen = false;
        }
        continue;
      }
      if (child.nodeType === Node.TEXT_NODE && !child.textContent.replace(/\u200b/g, "")) {
        continue;
      }
      seen = true;
    }
    segments.push({ start, end: host.childNodes.length });
    return segments;
  }

  function caretIndex(host, caret) {
    if (caret.startContainer === host) {
      return caret.startOffset;
    }
    let node = caret.startContainer;
    while (node.parentNode && node.parentNode !== host) {
      node = node.parentNode;
    }
    if (node.parentNode !== host) {
      return 0;
    }
    return [...host.childNodes].indexOf(node);
  }

  function segmentAt(host, caret) {
    const segments = quoteSegments(host);
    const index = caretIndex(host, caret);
    for (let position = 0; position < segments.length; position += 1) {
      const segment = segments[position];
      const last = position === segments.length - 1;
      if (index === segment.start || (index > segment.start && index < segment.end)) {
        return segment;
      }
      if (last && index >= segment.end) {
        return segment;
      }
    }
    return segments[segments.length - 1];
  }

  function segmentText(host, segment) {
    const range = document.createRange();
    range.setStart(host, segment.start);
    range.setEnd(host, Math.min(segment.end, host.childNodes.length));
    return range.toString().replace(/\u200b/g, "");
  }

  function emptyQuoteSegment(host, caret) {
    return segmentText(host, segmentAt(host, caret)).trim().length === 0;
  }

  function textBeforeQuoteSegment(quote, host, caret) {
    const range = document.createRange();
    range.setStart(quote, 0);
    range.setEnd(host, segmentAt(host, caret).start);
    return range.toString().replace(/\u200b/g, "");
  }

  function leaveEmptyQuoteLine(quote, host, caret) {
    const segment = segmentAt(host, caret);
    const breakBefore = segment.start > 0 ? host.childNodes[segment.start - 1] : null;
    const removeFrom = breakBefore && breakBefore.nodeName === "BR" ? segment.start - 1 : segment.start;
    for (let index = Math.min(segment.end, host.childNodes.length) - 1; index >= removeFrom; index -= 1) {
      host.childNodes[index].remove();
    }
    const rest = document.createElement("blockquote");
    let sibling = host.nextSibling;
    while (sibling) {
      const next = sibling.nextSibling;
      rest.appendChild(sibling);
      sibling = next;
    }
    if (!host.textContent.replace(/\u200b/g, "").trim() && !host.querySelector("br")) {
      host.remove();
    }
    const fresh = document.createElement("p");
    fresh.appendChild(document.createElement("br"));
    quote.after(fresh);
    if (rest.textContent.replace(/\u200b/g, "").trim() || rest.querySelector("br")) {
      fresh.after(rest);
    }
    if (!quote.textContent.replace(/\u200b/g, "").trim() && !quote.querySelector("br")) {
      quote.remove();
    }
    placeCaretAtStart(fresh);
  }

  function continueQuoteLine(host, caret) {
    const target = host && host.tagName === "P" ? host : host;
    const next = document.createElement("p");
    if (target && caret.startContainer && target.contains(caret.startContainer)) {
      const tail = document.createRange();
      tail.setStart(caret.startContainer, caret.startOffset);
      tail.setEnd(target, target.childNodes.length);
      next.appendChild(tail.extractContents());
    }
    while (next.firstChild && next.firstChild.nodeName === "BR") {
      next.firstChild.remove();
    }
    if (!next.childNodes.length) {
      next.appendChild(document.createElement("br"));
    }
    if (target && !target.childNodes.length) {
      target.appendChild(document.createElement("br"));
    }
    if (target.lastChild && target.lastChild.nodeName === "BR" && next.textContent.replace(/\u200b/g, "").trim()) {
      target.lastChild.remove();
    }
    if (target) {
      target.after(next);
    }
    placeCaretAtStart(next);
  }

  function placeCaretAtStart(element) {
    const point = document.createRange();
    point.setStart(element, 0);
    point.collapse(true);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(point);
  }

  function atBlockStart(block) {
    const selection = window.getSelection();
    if (!selection || !selection.rangeCount || !block.contains(selection.anchorNode)) {
      return false;
    }
    const range = selection.getRangeAt(0);
    const before = document.createRange();
    before.selectNodeContents(block);
    before.setEnd(range.startContainer, range.startOffset);
    return before.toString().replace(/\u200b/g, "").trim().length === 0;
  }

  function splitAfterCaret(block, tagName) {
    const selection = window.getSelection();
    const range = selection.getRangeAt(0);
    const tail = document.createRange();
    tail.setStart(range.startContainer, range.startOffset);
    tail.setEnd(block, block.childNodes.length);
    const extracted = tail.extractContents();
    const next = document.createElement(tagName);
    if (extracted.textContent.replace(/\u200b/g, "")) {
      next.appendChild(extracted);
    } else {
      next.appendChild(document.createElement("br"));
    }
    if (!block.textContent.replace(/\u200b/g, "")) {
      block.appendChild(document.createElement("br"));
    }
    block.after(next);
    const point = document.createRange();
    point.setStart(next, 0);
    point.collapse(true);
    selection.removeAllRanges();
    selection.addRange(point);
  }

  function insertEmptyMark(tag) {
    const selection = window.getSelection();
    const range = selection.getRangeAt(0);
    const mark = document.createElement(tag);
    mark.appendChild(document.createTextNode("\u200b"));
    range.insertNode(mark);
    const point = document.createRange();
    point.setStart(mark.firstChild, 1);
    point.collapse(true);
    selection.removeAllRanges();
    selection.addRange(point);
  }

  function marksInRange(range, selector) {
    const root = range.commonAncestorContainer;
    const scope = root.nodeType === Node.ELEMENT_NODE ? root : root.parentElement;
    if (!scope || !scope.querySelectorAll) {
      return [];
    }
    return [...scope.querySelectorAll(selector)].filter((mark) => range.intersectsNode(mark));
  }

  function rangeInside(range, element) {
    const probe = document.createRange();
    probe.selectNodeContents(element);
    return (
      range.compareBoundaryPoints(Range.START_TO_START, probe) >= 0 &&
      range.compareBoundaryPoints(Range.END_TO_END, probe) <= 0
    );
  }

  function removeMarkFromRange(element, range) {
    const before = document.createRange();
    before.selectNodeContents(element);
    before.setEnd(range.startContainer, range.startOffset);
    const after = document.createRange();
    after.selectNodeContents(element);
    after.setStart(range.endContainer, range.endOffset);
    const lead = before.cloneContents();
    const trail = after.cloneContents();
    const middle = range.extractContents();
    const leadSpace = peelEdge(lead, false);
    const trailSpace = peelEdge(trail, true);
    const fragment = document.createDocumentFragment();
    if (lead.textContent) {
      const opening = element.cloneNode(false);
      opening.appendChild(lead);
      fragment.appendChild(opening);
    }
    if (leadSpace) {
      fragment.appendChild(leadSpace);
    }
    fragment.appendChild(middle);
    if (trailSpace) {
      fragment.appendChild(trailSpace);
    }
    if (trail.textContent) {
      const closing = element.cloneNode(false);
      closing.appendChild(trail);
      fragment.appendChild(closing);
    }
    element.replaceWith(fragment);
  }

  function peelEdge(fragment, leading) {
    const node = leading ? fragment.firstChild : fragment.lastChild;
    if (!node || node.nodeType !== Node.TEXT_NODE) {
      return null;
    }
    const match = leading ? node.textContent.match(/^\s+/) : node.textContent.match(/\s+$/);
    if (!match) {
      return null;
    }
    const space = match[0];
    node.textContent = leading ? node.textContent.slice(space.length) : node.textContent.slice(0, -space.length);
    if (!node.textContent) {
      node.remove();
    }
    return document.createTextNode(space);
  }

  function wrapRangeUnifying(range, tag, selector) {
    const contents = range.extractContents();
    const nested = contents.querySelectorAll ? [...contents.querySelectorAll(selector)] : [];
    for (const mark of nested) {
      unwrap(mark);
    }
    const wrapper = document.createElement(tag);
    wrapper.appendChild(contents);
    range.insertNode(wrapper);
    const selection = window.getSelection();
    const next = document.createRange();
    next.selectNodeContents(wrapper);
    selection.removeAllRanges();
    selection.addRange(next);
  }

  function unwrapKeepCaret(element) {
    const selection = window.getSelection();
    const range = selection.getRangeAt(0);
    const before = document.createRange();
    before.setStart(element, 0);
    before.setEnd(range.startContainer, range.startOffset);
    const offset = before.toString().length;
    const text = element.textContent.replace(/\u200b/g, "");
    const node = document.createTextNode(text);
    element.replaceWith(node);
    const point = document.createRange();
    point.setStart(node, Math.min(offset, text.length));
    point.collapse(true);
    selection.removeAllRanges();
    selection.addRange(point);
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
    const text = preview.textContent.replace(/\u200b/g, "").trim();
    const structure = preview.querySelector("ul, ol, blockquote, pre, hr, table");
    preview.classList.toggle("is-blank", !text && !structure);
  }

  function htmlToMarkdown(root) {
    const parts = [];
    for (const node of root.childNodes) {
      const block = blockToMarkdown(node);
      if (block) {
        parts.push(block);
      }
    }
    let result = "";
    for (const part of parts) {
      if (!result) {
        result = part;
        continue;
      }
      const previous = result.split("\n").pop();
      result += (/^#{1,6} /.test(previous) ? "\n" : "\n\n") + part;
    }
    return result.replace(/\n{3,}/g, "\n\n").trim();
  }

  function blockToMarkdown(node) {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent.replace(/\u200b/g, "").replace(/\u00a0/g, " ").trim();
      return text || null;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return null;
    }
    const tag = node.tagName;
    if (tag === "SCRIPT" || tag === "STYLE") {
      return null;
    }
    if ((tag === "STRONG" || tag === "B" || tag === "EM" || tag === "I" || tag === "CODE" || tag === "A") && hasBlock(node)) {
      const inner = htmlToMarkdown(node);
      if (!inner) {
        return null;
      }
      if (tag === "A") {
        return "[" + inner + "](" + (node.getAttribute("href") || "") + ")";
      }
      if (tag === "CODE") {
        return "`" + inner + "`";
      }
      const mark = tag === "EM" || tag === "I" ? "*" : "**";
      return mark + inner + mark;
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
      const inner = quoteInner(node);
      if (inner == null) {
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

  function quoteInner(node) {
    const lines = [];
    let any = false;
    for (const child of node.childNodes) {
      if (child.nodeType === Node.TEXT_NODE) {
        const text = child.textContent.replace(/\u200b/g, "");
        if (!text.trim()) {
          continue;
        }
        lines.push(...text.replace(/\n$/, "").split("\n"));
        any = true;
        continue;
      }
      if (child.nodeType !== Node.ELEMENT_NODE) {
        continue;
      }
      if (child.tagName === "BR") {
        lines.push("");
        any = true;
        continue;
      }
      if (child.tagName === "P" || child.tagName === "DIV") {
        const onlyBreak = [...child.childNodes].every((part) => {
          return part.nodeName === "BR" || (part.nodeType === Node.TEXT_NODE && !part.textContent.replace(/\u200b/g, "").trim());
        });
        if (onlyBreak) {
          lines.push("");
          any = true;
          continue;
        }
        let text = inlineMarkdown(child).replace(/\u200b/g, "").replace(/[ \t]+\n/g, "\n");
        const endsWithBreak = child.lastChild && child.lastChild.nodeName === "BR";
        if (!endsWithBreak) {
          text = text.replace(/\n$/, "");
        }
        lines.push(...text.split("\n"));
        any = true;
        continue;
      }
      const block = blockToMarkdown(child);
      if (block) {
        lines.push(...block.split("\n"));
        any = true;
      }
    }
    return any ? lines.join("\n") : null;
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
      return node.textContent.replace(/\u200b/g, "");
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

  function restoreCaret(caret, textarea) {
    if (!caret || caret.kind !== "write") {
      return;
    }
    textarea.focus();
    textarea.setSelectionRange(caret.start, caret.end);
  }

  function placeRange(range) {
    const selection = window.getSelection();
    if (!range || !range.startContainer.isConnected) {
      return;
    }
    selection.removeAllRanges();
    selection.addRange(range);
  }

  // A collapsed caret turns the mark off for text typed next. Text already
  // inside the mark stays formatted.
  function leaveMark(element) {
    const selection = window.getSelection();
    if (!selection.rangeCount) {
      return;
    }
    const range = selection.getRangeAt(0);
    const tail = document.createRange();
    tail.setStart(range.startContainer, range.startOffset);
    tail.setEnd(element, element.childNodes.length);
    const extracted = tail.extractContents();
    const parent = element.parentNode;
    const following = element.nextSibling;
    const restHasContent = [...extracted.childNodes].some((node) => {
      return node.nodeType !== Node.TEXT_NODE || node.textContent.length > 0;
    });
    let rest = null;
    if (restHasContent) {
      rest = document.createElement(element.tagName.toLowerCase());
      if (element.hasAttribute("href")) {
        rest.setAttribute("href", element.getAttribute("href"));
      }
      rest.appendChild(extracted);
      parent.insertBefore(rest, following);
    }
    const point = document.createRange();
    if (!element.textContent) {
      const anchor = rest || following;
      parent.removeChild(element);
      if (anchor && anchor.isConnected) {
        point.setStartBefore(anchor);
      } else {
        point.selectNodeContents(parent);
        point.collapse(false);
      }
    } else {
      const holder = document.createTextNode("\u200b");
      parent.insertBefore(holder, element.nextSibling);
      point.setStart(holder, 1);
    }
    point.collapse(true);
    selection.removeAllRanges();
    selection.addRange(point);
  }

  function togglePreviewList(preview, ordered) {
    const selection = window.getSelection();
    const tag = ordered ? "OL" : "UL";
    if (!selection || !selection.rangeCount || !preview.contains(selection.anchorNode)) {
      insertEmptyList(preview, tag);
      return;
    }
    const range = selection.getRangeAt(0).cloneRange();
    const anchorItem = closestTag(selection.anchorNode, "li");
    const anchorList = anchorItem && preview.contains(anchorItem) ? anchorItem.closest("ul, ol") : null;
    if (selection.isCollapsed && anchorList) {
      if (anchorList.tagName === tag) {
        liftListItem(anchorItem);
      } else {
        renameList(anchorList, tag);
      }
      if (range.startContainer.isConnected) {
        placeRange(range);
      }
      return;
    }
    const blocks = blocksInRange(preview, selection);
    if (!blocks.length) {
      insertEmptyList(preview, tag);
      return;
    }
    const onlyList = blocks.length === 1 && blocks[0].nodeType === Node.ELEMENT_NODE && (blocks[0].tagName === "UL" || blocks[0].tagName === "OL");
    if (onlyList && blocks[0].tagName === tag) {
      const items = [...blocks[0].children].filter((item) => item.tagName === "LI" && range.intersectsNode(item));
      const targets = items.length ? items : [...blocks[0].querySelectorAll(":scope > li")];
      for (const item of targets.reverse()) {
        liftListItem(item);
      }
      if (range.startContainer.isConnected) {
        placeRange(range);
      }
      return;
    }
    if (onlyList) {
      renameList(blocks[0], tag);
      if (range.startContainer.isConnected) {
        placeRange(range);
      }
      return;
    }
    wrapBlocksAsList(blocks, tag);
    if (range.startContainer.isConnected) {
      placeRange(range);
    }
  }

  function insertEmptyList(preview, tag) {
    const list = document.createElement(tag.toLowerCase());
    const item = document.createElement("li");
    item.appendChild(document.createElement("br"));
    list.appendChild(item);
    preview.appendChild(list);
    const point = document.createRange();
    point.setStart(item, 0);
    point.collapse(true);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(point);
  }

  function renameList(list, tag) {
    if (list.tagName === tag) {
      return list;
    }
    const next = document.createElement(tag.toLowerCase());
    while (list.firstChild) {
      next.appendChild(list.firstChild);
    }
    list.replaceWith(next);
    return next;
  }

  function liftListItem(item) {
    const list = item.parentElement;
    const paragraph = document.createElement("p");
    while (item.firstChild) {
      paragraph.appendChild(item.firstChild);
    }
    if (!paragraph.childNodes.length) {
      paragraph.appendChild(document.createElement("br"));
    }
    const after = document.createElement(list.tagName.toLowerCase());
    let sibling = item.nextSibling;
    while (sibling) {
      const next = sibling.nextSibling;
      after.appendChild(sibling);
      sibling = next;
    }
    const parent = list.parentNode;
    item.remove();
    parent.insertBefore(paragraph, list.nextSibling);
    if (after.childNodes.length) {
      parent.insertBefore(after, paragraph.nextSibling);
    }
    if (!list.childNodes.length) {
      list.remove();
    }
    return paragraph;
  }

  function wrapBlocksAsList(blocks, tag) {
    const list = document.createElement(tag.toLowerCase());
    blocks[0].parentNode.insertBefore(list, blocks[0]);
    for (const block of blocks) {
      if (block.nodeType === Node.ELEMENT_NODE && (block.tagName === "UL" || block.tagName === "OL")) {
        while (block.firstChild) {
          const child = block.firstChild;
          if (child.tagName === "LI") {
            list.appendChild(child);
          } else {
            const item = document.createElement("li");
            item.appendChild(child);
            list.appendChild(item);
          }
        }
        block.remove();
        continue;
      }
      const item = document.createElement("li");
      if (block.nodeType === Node.TEXT_NODE) {
        item.appendChild(block);
      } else {
        while (block.firstChild) {
          item.appendChild(block.firstChild);
        }
        block.remove();
      }
      if (!item.childNodes.length) {
        item.appendChild(document.createElement("br"));
      }
      list.appendChild(item);
    }
    return list;
  }

  function blocksInRange(preview, selection) {
    const range = selection.getRangeAt(0);
    if (range.startContainer === preview || range.endContainer === preview) {
      const children = [...preview.childNodes];
      const from = range.startContainer === preview ? range.startOffset : 0;
      const to = range.endContainer === preview ? range.endOffset : children.length;
      return children.slice(from, to).filter((node) => node.nodeType === Node.ELEMENT_NODE || node.textContent.trim());
    }
    const start = topBlock(preview, range.startContainer);
    const end = topBlock(preview, range.endContainer);
    if (!start) {
      return [];
    }
    if (!end || start === end) {
      return [start];
    }
    const nodes = [...preview.childNodes];
    let from = nodes.indexOf(start);
    let to = nodes.indexOf(end);
    if (from < 0 || to < 0) {
      return [start];
    }
    if (from > to) {
      const swap = from;
      from = to;
      to = swap;
    }
    return nodes.slice(from, to + 1).filter((node) => node.nodeType === Node.ELEMENT_NODE || node.textContent.trim());
  }

  function topBlock(preview, node) {
    if (!node || node === preview || !preview.contains(node)) {
      return null;
    }
    let element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    if (!element || element === preview) {
      return node.nodeType === Node.TEXT_NODE ? node : null;
    }
    while (element.parentElement && element.parentElement !== preview) {
      element = element.parentElement;
    }
    return element.parentElement === preview ? element : null;
  }

  function replaceWithParagraph(heading) {
    const selection = window.getSelection();
    const range = selection.rangeCount ? selection.getRangeAt(0).cloneRange() : null;
    const paragraph = document.createElement("p");
    while (heading.firstChild) {
      paragraph.appendChild(heading.firstChild);
    }
    heading.replaceWith(paragraph);
    if (range && range.startContainer.isConnected) {
      placeRange(range);
    }
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
})();
