const NEEDS_CONNECTION = "Project settings need a connection.";
const CADENCES = [
  ["off", "Off"],
  ["weekly", "Weekly"],
  ["two_weeks", "Every 2 weeks"],
  ["monthly", "Monthly"],
  ["every_n_days", "Every N days"],
];

function prepareProjectUpdate({ name, description, cadence, days, ahead }) {
  const cleaned = String(name || "").trim();
  if (!cleaned) {
    return { error: "A project needs a name." };
  }
  if (cleaned.length > 200) {
    return { error: "A project name can be at most 200 characters." };
  }
  if (!CADENCES.some(([id]) => id === cadence)) {
    return { error: "That is not a sprint cadence." };
  }
  const body = {
    name: cleaned,
    description: String(description || "").trim(),
    sprint_cadence: cadence,
    sprint_ahead: wholeAhead(ahead),
  };
  if (body.sprint_ahead === null) {
    return { error: "Sprints in advance must be a whole number from 0 to 12." };
  }
  if (cadence === "every_n_days") {
    const count = wholeDays(days);
    if (count === null) {
      return { error: "Every N days needs a number of days of at least 1." };
    }
    body.sprint_cadence_days = count;
  }
  return { body };
}

function wholeAhead(value) {
  return wholeInRange(value, 0, 12);
}

function wholeDays(value) {
  return wholeInRange(value, 1, Number.MAX_SAFE_INTEGER);
}

function wholeInRange(value, minimum, maximum) {
  const text = String(value ?? "").trim();
  if (!/^\d+$/.test(text)) {
    return null;
  }
  const number = Number(text);
  if (!Number.isInteger(number) || number < minimum || number > maximum) {
    return null;
  }
  return number;
}

module.exports = {
  CADENCES,
  NEEDS_CONNECTION,
  prepareProjectUpdate,
};
