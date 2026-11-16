const test = require("node:test");
const assert = require("node:assert/strict");
const source = require("../../assets/js/markdown-source.js");

function caret(value) {
  const start = value.indexOf("^");
  const text = value.replace("^", "");
  return { text, start, end: start };
}

function range(value) {
  const start = value.indexOf("[");
  const end = value.indexOf("]");
  const text = value.replace("[", "").replace("]", "");
  return { text, start, end: end - 1 };
}

function apply(sample, action, ranged) {
  const picked = ranged ? range(sample) : caret(sample);
  return source.edit(picked.text, picked.start, picked.end, action);
}

test("write heading keeps the caret in the text", () => {
  assert.deepEqual(apply("^", "heading", false), { value: "## ", start: 3, end: 3 });
  assert.deepEqual(apply("Paint the ^door", "heading", false), { value: "## Paint the door", start: 13, end: 13 });
  assert.deepEqual(apply("## Paint the ^door", "heading", false), { value: "Paint the door", start: 10, end: 10 });
});

test("write quote follows the heading caret rule and only unquotes a mixed highlight", () => {
  assert.deepEqual(apply("^", "quote", false), { value: "> ", start: 2, end: 2 });
  assert.deepEqual(apply("Paint the ^door", "quote", false), { value: "> Paint the door", start: 12, end: 12 });
  assert.deepEqual(apply("> Paint the ^door", "quote", false), { value: "Paint the door", start: 10, end: 10 });
  assert.deepEqual(apply("Paint the [door]", "quote", true), { value: "> Paint the door", start: 12, end: 16 });
  assert.deepEqual(apply("> Paint the [door]", "quote", true), { value: "Paint the door", start: 10, end: 14 });
  const mixed = source.edit("Paint the door\n> Sand the frame", 0, "Paint the door\n> Sand the frame".length, "quote");
  assert.equal(mixed.value, "Paint the door\nSand the frame");
});

test("write lists keep the caret and toggle the prefix", () => {
  assert.deepEqual(apply("^", "bullet", false), { value: "- ", start: 2, end: 2 });
  assert.deepEqual(apply("Paint the ^door", "bullet", false), { value: "- Paint the door", start: 12, end: 12 });
  assert.deepEqual(apply("- Paint the ^door", "bullet", false), { value: "Paint the door", start: 10, end: 10 });
  assert.deepEqual(apply("^", "number", false), { value: "1. ", start: 3, end: 3 });
  assert.deepEqual(apply("Paint the ^door", "number", false), { value: "1. Paint the door", start: 13, end: 13 });
  assert.deepEqual(apply("1. Paint the ^door", "number", false), { value: "Paint the door", start: 10, end: 10 });
});

test("write bold follows the catalog examples", () => {
  assert.deepEqual(apply("^", "bold", false), { value: "****", start: 2, end: 2 });
  assert.deepEqual(apply("Paint the ^door", "bold", false), { value: "Paint the ****door", start: 12, end: 12 });
  assert.deepEqual(apply("**Paint the ^door**", "bold", false), { value: "Paint the door", start: 10, end: 10 });
  assert.deepEqual(apply("Paint the [door]", "bold", true), { value: "Paint the **door**", start: 12, end: 16 });
  assert.deepEqual(apply("**Paint [the] door**", "bold", true), { value: "**Paint** the **door**", start: 10, end: 13 });
  assert.deepEqual(apply("[hello **world**, how are you?]", "bold", true), {
    value: "**hello world, how are you?**",
    start: 2,
    end: 27,
  });
  const partial = apply("[hello **world] how are you?**", "bold", true);
  assert.equal(partial.value, "**hello \\*\\*world how are you?**");
  assert.equal(partial.start, 0);
  assert.equal(partial.value.slice(partial.start, partial.end), "**hello \\*\\*world");
});

test("write italic uses the bold rules with a single star", () => {
  assert.deepEqual(apply("Paint the [door]", "italic", true), { value: "Paint the *door*", start: 11, end: 15 });
});

test("write code wraps, fences a line break, and removes the marks", () => {
  assert.deepEqual(apply("^", "code", false), { value: "``", start: 1, end: 1 });
  assert.deepEqual(apply("`Paint the ^door`", "code", false), { value: "Paint the door", start: 10, end: 10 });
  assert.deepEqual(apply("`Paint [the] door`", "code", true), { value: "`Paint` the `door`", start: 8, end: 11 });
  const fenced = source.edit("one\ntwo", 0, 7, "code");
  assert.equal(fenced.value, "```\none\ntwo\n```");
});

test("write button state follows the marks the caret is in", () => {
  assert.equal(source.state("## Paint the door", 4, 4).heading, true);
  assert.equal(source.state("## Paint the **door**", 16, 16).bold, true);
  assert.equal(source.state("## Paint the door", 4, 4).bold, false);
  const mixed = "Paint the door\n> Sand the frame";
  assert.equal(source.state(mixed, 0, mixed.length).quote, true);
  const two = "See [the door](url) and [the frame](url)";
  assert.equal(source.state(two, 0, two.length).link, false);
});

test("write link unlinks one link and does nothing for two", () => {
  const plain = apply("[door]", "link", true);
  assert.equal(plain.value, "[door](url)");
  assert.equal(plain.value.slice(plain.start, plain.end), "url");
  const empty = apply("^", "link", false);
  assert.equal(empty.value, "[text](url)");
  assert.deepEqual(apply("[Paint the ^door](url)", "link", false), { value: "Paint the door", start: 10, end: 10 });
  const partial = "[Paint the door](url)";
  const partialAt = partial.indexOf("the");
  assert.deepEqual(source.edit(partial, partialAt, partialAt + 3, "link"), { value: "Paint the door", start: 0, end: 14 });
  const around = "See [the door](url) today";
  assert.equal(source.edit(around, 0, around.length, "link").value, "See the door today");
  const two = "See [the door](url) and [the frame](url)";
  assert.deepEqual(source.edit(two, 0, two.length, "link"), { value: two, start: 0, end: two.length });
});
