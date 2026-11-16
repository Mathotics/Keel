const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const { JSDOM } = require("jsdom");

const root = path.resolve(__dirname, "../..");

function boot(value) {
  const dom = new JSDOM(
    `<!doctype html><body><form>
      <span class="keel-md" data-keel-markdown>
        <span class="keel-md__bar">
          <button type="button" data-keel-md-tab="write">Write</button>
          <button type="button" data-keel-md-tab="preview">Preview</button>
          <button type="button" data-keel-md="heading">H</button>
          <button type="button" data-keel-md="bold">B</button>
          <button type="button" data-keel-md="italic">I</button>
          <button type="button" data-keel-md="quote">Q</button>
          <button type="button" data-keel-md="code">C</button>
          <button type="button" data-keel-md="link">Link</button>
          <button type="button" data-keel-md="bullet">•</button>
          <button type="button" data-keel-md="number">1.</button>
        </span>
        <textarea>${value}</textarea>
        <span class="keel-md__preview keel-markdown" hidden></span>
        <button class="keel-md__cancel" type="reset">Cancel</button>
        <button class="keel-md__save" type="submit">Save</button>
      </span>
    </form></body>`,
    { url: "http://127.0.0.1/", pretendToBeVisual: true, runScripts: "dangerously" },
  );
  const { window } = dom;
  window.document.execCommand = () => false;
  const dialogs = window.HTMLDialogElement.prototype;
  dialogs.showModal = function showModal() {
    this.open = true;
  };
  dialogs.close = function close(value) {
    this.returnValue = value == null ? "" : String(value);
    this.open = false;
    this.dispatchEvent(new window.Event("close"));
  };
  for (const file of ["assets/js/markdown-source.js", "assets/js/markdown-field.js"]) {
    const script = window.document.createElement("script");
    script.textContent = fs.readFileSync(path.join(root, file), "utf8");
    window.document.body.appendChild(script);
  }
  const editor = window.document.querySelector("[data-keel-markdown]");
  const textarea = editor.querySelector("textarea");
  const preview = editor.querySelector(".keel-md__preview");
  return { window, editor, textarea, preview };
}

function press(editor, action) {
  const button = editor.querySelector(`[data-keel-md="${action}"]`);
  button.dispatchEvent(new editor.ownerDocument.defaultView.MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  button.click();
}

function caretIn(preview, offset) {
  const window = preview.ownerDocument.defaultView;
  preview.focus();
  const walker = preview.ownerDocument.createTreeWalker(preview, window.NodeFilter.SHOW_TEXT);
  let seen = 0;
  let node = walker.nextNode();
  while (node) {
    const next = seen + node.textContent.length;
    if (offset <= next) {
      const range = preview.ownerDocument.createRange();
      range.setStart(node, offset - seen);
      range.collapse(true);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      preview.ownerDocument.dispatchEvent(new window.Event("selectionchange"));
      return;
    }
    seen = next;
    node = walker.nextNode();
  }
  throw new Error(`no caret at ${offset} in ${preview.textContent}`);
}

function selectContents(preview) {
  const window = preview.ownerDocument.defaultView;
  const range = preview.ownerDocument.createRange();
  range.selectNodeContents(preview);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  preview.ownerDocument.dispatchEvent(new window.Event("selectionchange"));
}

function enter(preview) {
  const window = preview.ownerDocument.defaultView;
  preview.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true }));
}

function previewFrom(value, html) {
  const box = boot(value);
  box.editor.classList.add("is-preview");
  box.preview.hidden = false;
  box.preview.innerHTML = html;
  return box;
}

test("preview enter splits a heading and leaves the new line unheaded", () => {
  const { preview, textarea } = previewFrom("## I am a heading", "<h2>I am a heading</h2>");
  caretIn(preview, "I am a ".length);
  enter(preview);
  assert.equal(textarea.value, "## I am a\nheading");
});

test("preview enter continues a quote and the next enter leaves that empty quote", () => {
  const box = previewFrom("> I am a quote", "<blockquote><p>I am a quote</p></blockquote>");
  caretIn(box.preview, "I am a quote".length);
  enter(box.preview);
  assert.equal(box.textarea.value, "> I am a quote\n>");
  enter(box.preview);
  assert.equal(box.textarea.value, "> I am a quote");
  const caret = box.window.getSelection().anchorNode;
  assert.equal(Boolean(caret && box.preview.querySelector("blockquote") && box.preview.querySelector("blockquote").contains(caret)), false);
});

test("preview keeps a blank line between quotes as two quotes", () => {
  const box = previewFrom(
    "> I am a quote\n\n> I am a quote too",
    "<blockquote><p>I am a quote</p></blockquote><blockquote><p>I am a quote too</p></blockquote>",
  );
  box.preview.dispatchEvent(new box.window.Event("input", { bubbles: true }));
  assert.equal(box.textarea.value, "> I am a quote\n\n> I am a quote too");
});

test("preview enter at the start of a quote or list removes that marker", () => {
  const sentence = "There is no text to the left of the caret";
  const quote = previewFrom("> " + sentence, "<blockquote><p>" + sentence + "</p></blockquote>");
  caretIn(quote.preview, 0);
  enter(quote.preview);
  assert.equal(quote.textarea.value, sentence);

  const bullet = previewFrom("- " + sentence, "<ul><li>" + sentence + "</li></ul>");
  caretIn(bullet.preview, 0);
  enter(bullet.preview);
  assert.equal(bullet.textarea.value, sentence);

  const numbered = previewFrom("1. " + sentence, "<ol><li>" + sentence + "</li></ol>");
  caretIn(numbered.preview, 0);
  enter(numbered.preview);
  assert.equal(numbered.textarea.value, sentence);
});

test("preview enter continues a numbered list and a bullet list", () => {
  const numbered = previewFrom("1. Hello World", "<ol><li>Hello World</li></ol>");
  caretIn(numbered.preview, "Hello ".length);
  enter(numbered.preview);
  assert.equal(numbered.textarea.value, "1. Hello\n2. World");

  const bullets = previewFrom("- Hello World", "<ul><li>Hello World</li></ul>");
  caretIn(bullets.preview, "Hello ".length);
  enter(bullets.preview);
  assert.equal(bullets.textarea.value, "- Hello\n- World");
});

test("preview heading is not bold, and clicking it again keeps bold text", () => {
  const box = previewFrom("## Paint the **door**", "<h2>Paint the <strong>door</strong></h2>");
  caretIn(box.preview, 1);
  assert.equal(box.editor.querySelector('[data-keel-md="bold"]').getAttribute("aria-pressed"), "false");
  assert.equal(box.editor.querySelector('[data-keel-md="heading"]').getAttribute("aria-pressed"), "true");
  press(box.editor, "heading");
  assert.equal(box.textarea.value, "Paint the **door**");
});

test("preview code removes the whole mark for a caret and only the highlight for a selection", () => {
  const caret = previewFrom("`hello world`", "<p><code>hello world</code></p>");
  caretIn(caret.preview, 6);
  press(caret.editor, "code");
  assert.equal(caret.textarea.value, "hello world");

  const partial = previewFrom("`Paint the door`", "<p><code>Paint the door</code></p>");
  const text = partial.preview.querySelector("code").firstChild;
  const range = partial.preview.ownerDocument.createRange();
  range.setStart(text, "Paint ".length);
  range.setEnd(text, "Paint the".length);
  const selection = partial.window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  press(partial.editor, "code");
  assert.equal(partial.textarea.value, "`Paint` the `door`");
});

test("preview bold makes a mixed highlight one bold span", () => {
  const box = previewFrom("hello **world**", "<p>hello <strong>world</strong></p>");
  const paragraph = box.preview.querySelector("p");
  const range = box.preview.ownerDocument.createRange();
  range.setStart(paragraph, 0);
  range.setEnd(paragraph, paragraph.childNodes.length);
  const selection = box.window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  press(box.editor, "bold");
  assert.equal(box.textarea.value, "**hello world**");
});

test("preview quote removes quotes and leaves plain lines plain", () => {
  const box = previewFrom("Paint the door\n\n> Sand the frame", "<p>Paint the door</p><blockquote><p>Sand the frame</p></blockquote>");
  selectContents(box.preview);
  press(box.editor, "quote");
  assert.equal(box.textarea.value, "Paint the door\n\nSand the frame");
});

test("preview link edits the whole link, and two links do nothing", () => {
  const one = previewFrom("See [the door](url) today", "<p>See <a href=\"url\">the door</a> today</p>");
  selectContents(one.preview);
  press(one.editor, "link");
  const dialog = one.window.document.querySelector(".keel-md__link-dialog");
  assert.equal(dialog.open, true);
  assert.equal(dialog.querySelector("[name='text']").value, "the door");
  assert.equal(dialog.querySelector("[name='link']").value, "url");
  dialog.close("cancel");
  assert.equal(one.textarea.value, "See [the door](url) today");
  selectContents(one.preview);
  press(one.editor, "link");
  dialog.querySelector("[name='text']").value = "the frame";
  dialog.querySelector("[name='link']").value = "https://example.test";
  dialog.close("ok");
  assert.equal(one.textarea.value, "See [the frame](https://example.test) today");

  const removed = previewFrom("See [the door](url) today", "<p>See <a href=\"url\">the door</a> today</p>");
  selectContents(removed.preview);
  press(removed.editor, "link");
  removed.window.document.querySelector(".keel-md__link-dialog").close("remove");
  assert.equal(removed.textarea.value, "See the door today");

  const partial = previewFrom("[Paint the door](url)", "<p><a href=\"url\">Paint the door</a></p>");
  const text = partial.preview.querySelector("a").firstChild;
  const range = partial.preview.ownerDocument.createRange();
  range.setStart(text, "Paint ".length);
  range.setEnd(text, "Paint the".length);
  const selection = partial.window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  press(partial.editor, "link");
  const partialDialog = partial.window.document.querySelector(".keel-md__link-dialog");
  assert.equal(partialDialog.querySelector("[name='text']").value, "Paint the door");
  partialDialog.close("cancel");

  const two = previewFrom(
    "See [the door](url) and [the frame](url)",
    "<p>See <a href=\"url\">the door</a> and <a href=\"url\">the frame</a></p>",
  );
  selectContents(two.preview);
  press(two.editor, "link");
  const twoDialog = two.window.document.querySelector(".keel-md__link-dialog");
  assert.equal(twoDialog, null);
  assert.equal(two.textarea.value, "See [the door](url) and [the frame](url)");
});

test("preview unbold leaves text already written and only turns the mark off afterward", () => {
  const box = previewFrom("hello **world**", "<p>hello <strong>world</strong></p>");
  caretIn(box.preview, "hello world".length);
  press(box.editor, "bold");
  assert.equal(box.textarea.value, "hello **world**");
});

test("check stays inactive until the text differs from what was loaded", () => {
  const { editor, textarea } = boot("Saved coats");
  const save = editor.querySelector(".keel-md__save");
  assert.equal(save.disabled, true);
  textarea.value = "Changed coats";
  textarea.dispatchEvent(new editor.ownerDocument.defaultView.Event("input", { bubbles: true }));
  assert.equal(save.disabled, false);
  textarea.value = "Saved coats";
  textarea.dispatchEvent(new editor.ownerDocument.defaultView.Event("input", { bubbles: true }));
  assert.equal(save.disabled, true);
});
