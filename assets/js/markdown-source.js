// Markdown source edits for the Write tab. Each change is the catalog row for
// that button: the caret stays in the same place in the text, a complete bold
// overlap becomes one span, and a partial overlap escapes the marker it cuts.
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.KeelMarkdownSource = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function edit(value, start, end, action) {
    if (action === "bold") {
      return editMark(value, start, end, "**");
    }
    if (action === "italic") {
      return editMark(value, start, end, "*");
    }
    if (action === "code") {
      return editCode(value, start, end);
    }
    if (action === "link") {
      return editLink(value, start, end);
    }
    if (action === "heading" || action === "quote" || action === "bullet" || action === "number") {
      return editPrefix(value, start, end, action);
    }
    return { value: value, start: start, end: end };
  }

  function state(value, start, end) {
    const block = lineBlock(value, start, end);
    const emphasis = emphasisAt(value, start, end);
    return {
      heading: block.lines.some((line) => lineKind(line) === "heading"),
      bold: !!emphasis.bold && !partialMark(value, start, end, "**"),
      italic: !!emphasis.italic && !partialMark(value, start, end, "*"),
      quote: block.lines.some((line) => lineKind(line) === "quote"),
      code: !!fenceAround(value, start, end) || !!emphasis.code,
      link: linkState(value, start, end),
      bullet: block.lines.some((line) => lineKind(line) === "bullet"),
      number: block.lines.some((line) => lineKind(line) === "number"),
    };
  }

  function editPrefix(value, start, end, kind) {
    const block = lineBlock(value, start, end);
    const kinds = block.lines.map(lineKind);
    const quoteMixed = kind === "quote" && kinds.some((item) => item === "quote") && kinds.some((item) => item !== "quote");
    const nextLines = block.lines.map((line, index) => rewriteLine(line, index, kind, quoteMixed));
    const next = value.slice(0, block.start) + nextLines.join("\n") + value.slice(block.end);
    return {
      value: next,
      start: mapOffset(block, nextLines, start),
      end: mapOffset(block, nextLines, end),
    };
  }

  function rewriteLine(line, index, kind, quoteMixed) {
    if (quoteMixed) {
      return lineKind(line) === "quote" ? stripKind(line) : line;
    }
    if (lineKind(line) === kind) {
      return stripKind(line);
    }
    return addPrefix(kind, index, stripKind(line));
  }

  function addPrefix(kind, index, text) {
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
  }

  function mapOffset(block, nextLines, offset) {
    let oldPos = block.start;
    let newPos = block.start;
    for (let index = 0; index < block.lines.length; index += 1) {
      const oldLine = block.lines[index];
      const nextLine = nextLines[index];
      const oldEnd = oldPos + oldLine.length;
      if (offset <= oldEnd || index === block.lines.length - 1) {
        const within = Math.max(0, Math.min(offset - oldPos, oldLine.length));
        const oldPrefix = prefixLength(oldLine);
        const textOffset = Math.max(0, within - oldPrefix);
        return newPos + prefixLength(nextLine) + textOffset;
      }
      oldPos = oldEnd + 1;
      newPos += nextLine.length + 1;
    }
    return newPos;
  }

  function prefixLength(line) {
    const number = line.match(/^\d+\. /);
    if (number) {
      return number[0].length;
    }
    if (line.startsWith("- ") || line.startsWith("> ")) {
      return 2;
    }
    if (line.startsWith("## ")) {
      return 3;
    }
    return 0;
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

  function editMark(value, start, end, mark) {
    const block = lineBlock(value, start, end);
    let next = value;
    let shift = 0;
    let newStart = start;
    let newEnd = end;
    let cursor = block.start;
    for (let index = 0; index < block.lines.length; index += 1) {
      const line = block.lines[index];
      const lineStart = cursor;
      const lineEnd = cursor + line.length;
      const collapsed = start === end;
      const touches = collapsed ? start >= lineStart && start <= lineEnd : start < lineEnd && end > lineStart;
      if (touches) {
        const from = collapsed ? start - lineStart : Math.max(0, start - lineStart);
        const to = collapsed ? end - lineStart : Math.min(line.length, end - lineStart);
        const result = editMarkLine(line, from, to, mark);
        const at = lineStart + shift;
        next = next.slice(0, at) + result.line + next.slice(at + line.length);
        const delta = result.line.length - line.length;
        if (start >= lineStart && start <= lineEnd) {
          newStart = at + result.start;
        } else if (start > lineEnd) {
          newStart += delta;
        }
        if (end >= lineStart && end <= lineEnd) {
          newEnd = at + result.end;
        } else if (end > lineEnd) {
          newEnd += delta;
        }
        shift += delta;
      }
      cursor = lineEnd + 1;
    }
    return { value: next, start: newStart, end: newEnd };
  }

  function editMarkLine(line, start, end, mark) {
    const pairs = findPairs(line, mark);
    if (start === end) {
      const hit = pairs.find((pair) => start >= pair.innerStart && start <= pair.innerEnd);
      if (!hit) {
        const next = line.slice(0, start) + mark + mark + line.slice(start);
        return { line: next, start: start + mark.length, end: start + mark.length };
      }
      const next = line.slice(0, hit.open) + line.slice(hit.innerStart, hit.innerEnd) + line.slice(hit.closeEnd);
      const caret = start - mark.length;
      return { line: next, start: caret, end: caret };
    }
    const partials = pairs.filter((pair) => splitsPair(pair, start, end));
    if (partials.length) {
      return escapePartial(line, start, end, mark);
    }
    const container = pairs.find((pair) => start >= pair.innerStart && end <= pair.innerEnd);
    if (container) {
      return splitPair(line, start, end, mark, container);
    }
    const contained = pairs.filter((pair) => pair.open >= start && pair.closeEnd <= end);
    if (contained.length) {
      return mergePairs(line, start, end, mark, contained);
    }
    const selected = line.slice(start, end);
    const next = line.slice(0, start) + mark + selected + mark + line.slice(end);
    return { line: next, start: start + mark.length, end: end + mark.length };
  }

  function splitsPair(pair, start, end) {
    const openInside = pair.open >= start && pair.open < end;
    const closeInside = pair.close >= start && pair.close < end;
    return openInside !== closeInside;
  }

  function escapePartial(line, start, end, mark) {
    const pairs = findPairs(line, mark);
    const tokens = [];
    for (const pair of pairs) {
      if (pair.open >= start && pair.open + mark.length <= end) {
        tokens.push(pair.open);
      }
      if (pair.close >= start && pair.close + mark.length <= end) {
        tokens.push(pair.close);
      }
    }
    tokens.sort((left, right) => right - left);
    let selected = line.slice(start, end);
    for (const token of tokens) {
      const at = token - start;
      selected = selected.slice(0, at) + escaped(mark) + selected.slice(at + mark.length);
    }
    const openInside = pairs.some((pair) => pair.open >= start && pair.open < end && pair.close >= end);
    const closeInside = pairs.some((pair) => pair.close >= start && pair.close < end && pair.open < start);
    if (openInside) {
      selected = mark + selected;
    }
    if (closeInside) {
      selected = selected + mark;
    }
    const next = line.slice(0, start) + selected + line.slice(end);
    return { line: next, start: start, end: start + selected.length };
  }

  function escaped(mark) {
    return mark === "**" ? "\\*\\*" : mark === "*" ? "\\*" : "\\`";
  }

  function splitPair(line, start, end, mark, pair) {
    const inner = line.slice(pair.innerStart, pair.innerEnd);
    const before = inner.slice(0, start - pair.innerStart);
    const selected = inner.slice(start - pair.innerStart, end - pair.innerStart);
    const after = inner.slice(end - pair.innerStart);
    const beforeTrim = before.replace(/\s+$/, "");
    const beforeSpace = before.slice(beforeTrim.length);
    const afterTrim = after.replace(/^\s+/, "");
    const afterSpace = after.slice(0, after.length - afterTrim.length);
    let built = "";
    if (beforeTrim) {
      built += mark + beforeTrim + mark;
    }
    const selectedAt = built.length + beforeSpace.length;
    built += beforeSpace + selected + afterSpace;
    if (afterTrim) {
      built += mark + afterTrim + mark;
    }
    if (start === pair.innerStart && end === pair.innerEnd) {
      const plain = line.slice(0, pair.open) + inner + line.slice(pair.closeEnd);
      return { line: plain, start: pair.open, end: pair.open + inner.length };
    }
    const next = line.slice(0, pair.open) + built + line.slice(pair.closeEnd);
    return { line: next, start: pair.open + selectedAt, end: pair.open + selectedAt + selected.length };
  }

  function mergePairs(line, start, end, mark, pairs) {
    let selected = line.slice(start, end);
    const outside = selected.length > 0 && pairs.every((pair) => pair.open > start || pair.closeEnd < end);
    const tokens = [];
    for (const pair of pairs) {
      tokens.push(pair.open - start, pair.close - start);
    }
    tokens.sort((left, right) => right - left);
    for (const token of tokens) {
      selected = selected.slice(0, token) + selected.slice(token + mark.length);
    }
    if (!outside) {
      const next = line.slice(0, start) + selected + line.slice(end);
      return { line: next, start: start, end: start + selected.length };
    }
    const wrapped = mark + selected + mark;
    const next = line.slice(0, start) + wrapped + line.slice(end);
    return { line: next, start: start + mark.length, end: start + mark.length + selected.length };
  }

  function findPairs(line, mark) {
    const tokens = [];
    let index = 0;
    while (index < line.length) {
      if (line.charAt(index) === "\\") {
        index += 2;
        continue;
      }
      if (mark === "*" && line.startsWith("**", index)) {
        index += 2;
        continue;
      }
      if (line.startsWith(mark, index)) {
        tokens.push(index);
        index += mark.length;
        continue;
      }
      index += 1;
    }
    const pairs = [];
    for (let cursor = 0; cursor + 1 < tokens.length; cursor += 2) {
      const open = tokens[cursor];
      const close = tokens[cursor + 1];
      pairs.push({
        open: open,
        close: close,
        innerStart: open + mark.length,
        innerEnd: close,
        closeEnd: close + mark.length,
      });
    }
    return pairs;
  }

  function partialMark(value, start, end, mark) {
    if (start === end) {
      return false;
    }
    const block = lineBlock(value, start, end);
    let cursor = block.start;
    for (const line of block.lines) {
      const from = Math.max(0, start - cursor);
      const to = Math.min(line.length, end - cursor);
      if (from < to && findPairs(line, mark).some((pair) => splitsPair(pair, from, to))) {
        return true;
      }
      cursor += line.length + 1;
    }
    return false;
  }

  function emphasisAt(value, start, end) {
    const fence = fenceAround(value, start, end);
    if (fence) {
      return { bold: null, italic: null, code: null };
    }
    const block = lineBlock(value, start, end);
    const line = block.lines[0];
    const relStart = start - block.start;
    const relEnd = end - block.start;
    return {
      bold: covering(findPairs(line, "**"), relStart, relEnd),
      italic: covering(findPairs(line, "*"), relStart, relEnd),
      code: covering(findPairs(line, "`"), relStart, relEnd),
    };
  }

  function covering(pairs, start, end) {
    return (
      pairs.find((pair) => {
        if (start === end) {
          return start >= pair.innerStart && start <= pair.innerEnd;
        }
        const inside = start >= pair.innerStart && end <= pair.innerEnd;
        const around = start <= pair.open && end >= pair.closeEnd;
        return inside || around;
      }) || null
    );
  }

  function editCode(value, start, end) {
    const fence = fenceAround(value, start, end);
    if (fence) {
      const inner = fenceText(value, fence);
      return { value: value.slice(0, fence.open) + inner + value.slice(fence.close), start: fence.open, end: fence.open + inner.length };
    }
    if (start !== end && value.slice(start, end).indexOf("\n") !== -1) {
      const selected = value.slice(start, end);
      const fenced = "```\n" + selected + "\n```";
      return { value: value.slice(0, start) + fenced + value.slice(end), start: start + 4, end: start + 4 + selected.length };
    }
    return editMark(value, start, end, "`");
  }

  function fenceText(value, fence) {
    let innerStart = value.indexOf("\n", fence.open);
    innerStart = innerStart < 0 ? fence.open + 3 : innerStart + 1;
    let innerEnd = value.lastIndexOf("\n", fence.close - 1);
    if (innerEnd < fence.open) {
      innerEnd = fence.close - 3;
    }
    return value.slice(innerStart, innerEnd).replace(/\n$/, "");
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
          return { open: open, close: close };
        }
        open = -1;
      }
      index += 2;
    }
    return null;
  }

  function editLink(value, start, end) {
    const links = findLinks(value);
    const contained = links.filter((link) => link.open >= start && link.close <= end);
    if (start !== end && contained.length >= 2) {
      return { value: value, start: start, end: end };
    }
    if (start !== end && contained.length === 1 && (contained[0].open > start || contained[0].close < end)) {
      return replaceLink(value, contained[0], start, end);
    }
    const inside = links.find((link) => start >= link.open && end <= link.close);
    if (inside) {
      return replaceLink(value, inside, start, end);
    }
    const selected = value.slice(start, end) || "text";
    const inserted = "[" + selected + "](url)";
    const urlAt = start + selected.length + 3;
    return {
      value: value.slice(0, start) + inserted + value.slice(end),
      start: urlAt,
      end: urlAt + 3,
    };
  }

  function replaceLink(value, link, start, end) {
    const next = value.slice(0, link.open) + link.text + value.slice(link.close);
    if (start === end) {
      const within = Math.max(0, Math.min(start - link.textStart, link.text.length));
      const caret = link.open + within;
      return { value: next, start: caret, end: caret };
    }
    return { value: next, start: link.open, end: link.open + link.text.length };
  }

  function findLinks(value) {
    const links = [];
    const pattern = /\[([^\[\]]*)\]\(([^)]*)\)/g;
    let match = pattern.exec(value);
    while (match) {
      links.push({
        open: match.index,
        close: match.index + match[0].length,
        textStart: match.index + 1,
        text: match[1],
      });
      match = pattern.exec(value);
    }
    return links;
  }

  function linkState(value, start, end) {
    const links = findLinks(value);
    if (links.filter((link) => link.open >= start && link.close <= end).length >= 2) {
      return false;
    }
    return links.some((link) => {
      const caret = start === end && start >= link.open && start <= link.close;
      const selected = start !== end && start < link.close && end > link.open;
      return caret || selected;
    });
  }

  return { edit: edit, state: state };
});
