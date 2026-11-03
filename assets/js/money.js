// A cost field shows "$12.50 USD" until it is edited. Focus leaves the number.
// Blur puts the symbol and code back. Leaving the number unchanged does not
// submit, so opening a zero field does not store zero.
function isDigit(char) {
  return char >= "0" && char <= "9";
}

function isLetter(char) {
  const code = char.charCodeAt(0);
  return (code >= 65 && code <= 90) || (code >= 97 && code <= 122);
}

function bareAmount(value) {
  let text = String(value || "").trim();
  if (
    text.length >= 3 &&
    isLetter(text.charAt(text.length - 1)) &&
    isLetter(text.charAt(text.length - 2)) &&
    isLetter(text.charAt(text.length - 3))
  ) {
    text = text.slice(0, -3).trim();
  }
  let start = 0;
  while (start < text.length && !isDigit(text.charAt(start))) {
    start += 1;
  }
  let digits = "";
  for (let index = start; index < text.length; index += 1) {
    const char = text.charAt(index);
    if (char !== ",") {
      digits += char;
    }
  }
  return digits;
}

function amountKey(value) {
  const number = bareAmount(value);
  if (!number) {
    return "";
  }
  let dot = false;
  for (const char of number) {
    if (char === ".") {
      if (dot) {
        return null;
      }
      dot = true;
      continue;
    }
    if (!isDigit(char)) {
      return null;
    }
  }
  const split = number.indexOf(".");
  let whole = split === -1 ? number : number.slice(0, split);
  let fraction = split === -1 ? "" : number.slice(split + 1);
  if (fraction.length > 2) {
    return null;
  }
  fraction = `${fraction}00`.slice(0, 2);
  while (whole.length > 1 && whole.charAt(0) === "0") {
    whole = whole.slice(1);
  }
  return `${whole}.${fraction}`;
}

function sameAmount(left, right) {
  const first = amountKey(left);
  const second = amountKey(right);
  return first !== null && first !== "" && first === second;
}

function groupThousands(value) {
  const parts = [];
  let rest = String(value);
  while (rest.length > 3) {
    parts.unshift(rest.slice(-3));
    rest = rest.slice(0, -3);
  }
  parts.unshift(rest);
  return parts.join(",");
}

function labeledAmount(value, symbol, code) {
  const key = amountKey(value);
  if (!key) {
    return String(value || "");
  }
  const split = key.indexOf(".");
  const whole = key.slice(0, split);
  const fraction = key.slice(split + 1);
  return `${symbol || ""}${groupThousands(whole)}.${fraction} ${code || "USD"}`;
}

function bindMoneyFields(doc) {
  const restoreUnchanged = (event) => {
    const input = event.target;
    if (!input || !input.hasAttribute || !input.hasAttribute("data-keel-money")) {
      return;
    }
    const idle = input.dataset.moneyIdle || "";
    if (!sameAmount(input.value, idle)) {
      return;
    }
    input.value = idle;
    event.stopPropagation();
  };

  doc.addEventListener("change", restoreUnchanged, true);

  for (const input of doc.querySelectorAll("[data-keel-money]")) {
    input.addEventListener("focus", () => {
      input.dataset.moneyIdle = input.value;
      const bare = bareAmount(input.value);
      if (bare !== input.value) {
        input.value = bare;
        input.select();
      }
    });
    input.addEventListener("blur", () => {
      const idle = input.dataset.moneyIdle || "";
      if (sameAmount(input.value, idle)) {
        input.value = idle;
        return;
      }
      input.value = labeledAmount(
        input.value,
        input.dataset.currencySymbol || "",
        input.dataset.currencyCode || "USD",
      );
    });
  }
}

if (typeof document !== "undefined") {
  bindMoneyFields(document);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { bareAmount, labeledAmount, sameAmount };
}
