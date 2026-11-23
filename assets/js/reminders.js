// Arms reminder timers while this tab is open. A closed tab stays quiet.
(() => {
  const stack = document.querySelector("#keel-reminders");
  if (!stack) {
    return;
  }
  const seenKey = "keel.reminder.seen";
  const timers = new Set();

  const seen = () => {
    try {
      return JSON.parse(localStorage.getItem(seenKey) || "{}");
    } catch {
      return {};
    }
  };

  const remember = (key) => {
    const current = seen();
    current[key] = true;
    localStorage.setItem(seenKey, JSON.stringify(current));
  };

  const fireKey = (fire) =>
    `${fire.issue_id}|${fire.at}|${fire.catch_up ? "catch" : "plan"}|${fire.reasons.join("|")}`;

  const parseWall = (value) => {
    const text = String(value || "");
    if (text.length < 16) {
      return null;
    }
    const year = Number(text.slice(0, 4));
    const month = Number(text.slice(5, 7));
    const day = Number(text.slice(8, 10));
    const hour = Number(text.slice(11, 13));
    const minute = Number(text.slice(14, 16));
    const second = text[16] === ":" ? Number(text.slice(17, 19)) : 0;
    const parts = [year, month, day, hour, minute, second];
    if (text[4] !== "-" || text[7] !== "-" || (text[10] !== "T" && text[10] !== " ")) {
      return null;
    }
    if (text[13] !== ":" || parts.some((part) => !Number.isInteger(part))) {
      return null;
    }
    return new Date(year, month - 1, day, hour, minute, second);
  };

  const showCard = (fire) => {
    const key = fireKey(fire);
    if (seen()[key]) {
      return;
    }
    const card = document.createElement("article");
    card.className = "keel-reminder-card";
    const title = document.createElement("p");
    const link = document.createElement("a");
    link.href = `/issues/${fire.issue_key}`;
    link.textContent = `${fire.issue_key} ${fire.issue_title}`;
    title.append(link);
    const body = document.createElement("p");
    body.textContent = fire.reasons.join(". ");
    card.append(title, body);
    if (fire.reasons.includes("Overdue")) {
      const when = document.createElement("input");
      when.type = "datetime-local";
      const snooze = document.createElement("button");
      snooze.type = "button";
      snooze.textContent = "Snooze";
      snooze.addEventListener("click", () => {
        if (!when.value) {
          return;
        }
        send(fire.issue_id, "PUT", "/snooze", { until: when.value });
        remember(key);
        card.remove();
      });
      const dismiss = document.createElement("button");
      dismiss.type = "button";
      dismiss.textContent = "Dismiss";
      dismiss.addEventListener("click", () => {
        send(fire.issue_id, "POST", "/dismiss-overdue", {});
        remember(key);
        card.remove();
      });
      card.append(when, snooze, dismiss);
    }
    stack.hidden = false;
    stack.append(card);
    notify(fire);
    remember(key);
  };

  const notify = (fire) => {
    if (!("Notification" in window) || Notification.permission !== "granted") {
      return;
    }
    const notice = new Notification(`${fire.issue_key} ${fire.reasons[0]}`, {
      body: `${fire.issue_title}. ${fire.reasons.join(". ")}`,
      tag: `keel-${fire.issue_id}-${fire.at}`,
    });
    notice.onclick = () => {
      window.focus();
      window.location.href = `/issues/${fire.issue_key}`;
    };
  };

  const send = (issueId, method, path, body) => {
    fetch(`/api/v1/issues/${issueId}/reminder${path}`, {
      method,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    }).catch(() => {});
  };

  const permissionNote = () => {
    if (!("Notification" in window) || Notification.permission !== "denied") {
      return;
    }
    const note = document.createElement("p");
    note.className = "keel-note";
    note.textContent =
      "Browser reminders are blocked. Allow notifications for this site. This page still shows a reminder while it is open.";
    stack.hidden = false;
    stack.append(note);
  };

  const arm = (fires) => {
    timers.forEach((timer) => clearTimeout(timer));
    timers.clear();
    const now = Date.now();
    fires.forEach((fire) => {
      const at = parseWall(fire.at);
      if (!at) {
        return;
      }
      const delay = at.getTime() - now;
      if (fire.catch_up || delay <= 0) {
        showCard(fire);
        return;
      }
      const timer = setTimeout(() => showCard(fire), delay);
      timers.add(timer);
    });
  };

  const refresh = () => {
    fetch("/api/v1/reminders/schedule?catch_up=true", {
      headers: { Accept: "application/json" },
    })
      .then((response) => (response.ok ? response.json() : null))
      .then((fires) => {
        if (!Array.isArray(fires)) {
          return;
        }
        if ("Notification" in window && Notification.permission === "default" && fires.length) {
          Notification.requestPermission().catch(() => {});
        }
        arm(fires);
      })
      .catch(() => {});
  };

  document.querySelectorAll("[data-keel-add-offset]").forEach((button) => {
    button.addEventListener("click", () => {
      const name = button.getAttribute("data-keel-add-offset");
      const row = button.parentElement
        && button.parentElement.parentElement
        && button.parentElement.parentElement.querySelector(`[name="${name}_amount"]`);
      const holder = row && row.closest("[data-keel-offset-row]");
      if (!holder) {
        return;
      }
      const copy = holder.cloneNode(true);
      copy.querySelectorAll("input").forEach((input) => {
        input.value = "";
      });
      holder.parentElement.insertBefore(copy, button.parentElement);
    });
  });

  permissionNote();
  refresh();
  setInterval(refresh, 60000);
})();
