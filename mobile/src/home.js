const { SECTIONS } = require("./inbox");

const ALL_HIDDEN = "Every home panel is hidden.";
const KEYS = SECTIONS.map(([key]) => key);
const TITLES = Object.fromEntries(SECTIONS);

function blankLayout() {
  return { order: KEYS.slice(), hidden: [] };
}

function normalizeLayout(layout) {
  const hidden = KEYS.filter((key) => ((layout && layout.hidden) || []).includes(key));
  const removed = new Set(hidden);
  const order = [];
  for (const key of (layout && layout.order) || []) {
    if (KEYS.includes(key) && !removed.has(key) && !order.includes(key)) {
      order.push(key);
    }
  }
  for (const key of KEYS) {
    if (!order.includes(key) && !removed.has(key)) {
      order.push(key);
    }
  }
  return { order, hidden };
}

function parseLayout(raw) {
  if (!raw) {
    return blankLayout();
  }
  try {
    return normalizeLayout(JSON.parse(raw));
  } catch {
    return blankLayout();
  }
}

function homeKey(userId) {
  return `keel.home.${userId}`;
}

function hideSection(layout, key) {
  const current = normalizeLayout(layout);
  if (!KEYS.includes(key) || current.hidden.includes(key)) {
    return current;
  }
  return normalizeLayout({
    order: current.order.filter((item) => item !== key),
    hidden: [...current.hidden, key],
  });
}

function showSection(layout, key) {
  const current = normalizeLayout(layout);
  if (!KEYS.includes(key) || !current.hidden.includes(key)) {
    return current;
  }
  return normalizeLayout({
    order: [...current.order.filter((item) => item !== key), key],
    hidden: current.hidden.filter((item) => item !== key),
  });
}

function moveSection(layout, visible, key, direction) {
  const current = normalizeLayout(layout);
  const items = [];
  for (const item of visible || []) {
    if (current.order.includes(item) && !current.hidden.includes(item) && !items.includes(item)) {
      items.push(item);
    }
  }
  const index = items.indexOf(key);
  const neighbour = direction === "up" ? index - 1 : direction === "down" ? index + 1 : -1;
  if (index < 0 || neighbour < 0 || neighbour >= items.length) {
    return current;
  }
  const swapped = items.slice();
  const held = swapped[index];
  swapped[index] = swapped[neighbour];
  swapped[neighbour] = held;
  const shown = new Set(swapped);
  const queue = swapped.slice();
  return {
    order: current.order.map((item) => (shown.has(item) ? queue.shift() : item)),
    hidden: current.hidden,
  };
}

function arrangeInbox(view, layout) {
  if (!view) {
    return null;
  }
  const saved = normalizeLayout(layout);
  const byKey = new Map((view.sections || []).map((section) => [section.key, section]));
  const sections = [];
  for (const key of saved.order) {
    if (saved.hidden.includes(key)) {
      continue;
    }
    const section = byKey.get(key);
    if (section) {
      sections.push(section);
    }
  }
  const removed = saved.hidden.map((key) => ({ key, title: TITLES[key] }));
  const allHidden = !view.empty && (view.sections || []).length > 0 && !sections.length;
  return {
    ...view,
    sections,
    hidden: removed,
    allHidden: allHidden ? ALL_HIDDEN : "",
    empty: allHidden ? "" : view.empty,
  };
}

module.exports = {
  ALL_HIDDEN,
  arrangeInbox,
  blankLayout,
  hideSection,
  homeKey,
  moveSection,
  parseLayout,
  showSection,
};
