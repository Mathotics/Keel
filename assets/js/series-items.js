(function () {
  var root = document.querySelector("[data-series-items]");
  var hidden = document.querySelector("[data-series-items-json]");
  var configNode = document.getElementById("series-items-config");
  if (!root || !hidden || !configNode) {
    return;
  }
  var config = JSON.parse(configNode.textContent || "{}");
  var items = JSON.parse(hidden.value || "[]");
  if (!Array.isArray(items)) {
    items = [];
  }
  var nextKey = 1;
  var fieldId = 1;

  function keyOf(item) {
    return item.key || (item.id ? "id:" + item.id : "");
  }

  function depth(item, guard) {
    if (!item.parent_key || guard > 8) {
      return 0;
    }
    var parent = items.find(function (row) {
      return keyOf(row) === item.parent_key;
    });
    return parent ? 1 + depth(parent, guard + 1) : 0;
  }

  function write() {
    hidden.value = JSON.stringify(items);
  }

  function field(label, node) {
    var wrap = document.createElement("p");
    var caption = document.createElement("label");
    caption.textContent = label;
    if (!node.id) {
      node.id = "series-item-field-" + fieldId++;
    }
    caption.htmlFor = node.id;
    wrap.appendChild(caption);
    wrap.appendChild(node);
    return wrap;
  }

  function select(options, value) {
    var node = document.createElement("select");
    options.forEach(function (option) {
      var choice = document.createElement("option");
      choice.value = option.value;
      choice.textContent = option.label;
      if (String(option.value) === String(value == null ? "" : value)) {
        choice.selected = true;
      }
      node.appendChild(choice);
    });
    return node;
  }

  function textInput(value) {
    var node = document.createElement("input");
    node.type = "text";
    node.value = value || "";
    return node;
  }

  function render() {
    root.replaceChildren();
    items.forEach(function (item, index) {
      if (!item.key) {
        item.key = item.id ? "id:" + item.id : "new:" + nextKey++;
      }
      var card = document.createElement("div");
      card.className = "keel-series-item";
      card.style.marginLeft = depth(item, 0) * 16 + "px";
      var title = textInput(item.title);
      title.required = true;
      title.maxLength = 300;
      title.addEventListener("input", function () {
        item.title = title.value;
        write();
      });
      var description = document.createElement("textarea");
      description.rows = 2;
      description.value = item.description || "";
      description.addEventListener("input", function () {
        item.description = description.value;
        write();
      });
      var type = select(config.types || [], item.type || "story");
      type.addEventListener("change", function () {
        item.type = type.value;
        write();
      });
      var priority = select(config.priorities || [], item.priority || "p4");
      priority.addEventListener("change", function () {
        item.priority = priority.value;
        write();
      });
      var labels = textInput((item.labels || []).join(", "));
      labels.addEventListener("input", function () {
        item.labels = labels.value.split(",").map(function (part) {
          return part.trim();
        }).filter(Boolean);
        write();
      });
      var people = [{ value: "", label: "Unassigned" }].concat(
        (config.users || []).map(function (person) {
          return { value: String(person.id), label: person.name };
        }),
      );
      var assignee = select(people, item.assignee_id == null ? "" : item.assignee_id);
      assignee.addEventListener("change", function () {
        item.assignee_id = assignee.value ? Number(assignee.value) : null;
        write();
      });
      var parents = [{ value: "", label: "Under the root" }].concat(
        items.filter(function (row) {
          return keyOf(row) !== keyOf(item);
        }).map(function (row) {
          return { value: keyOf(row), label: row.title || "Untitled" };
        }),
      );
      var parent = select(parents, item.parent_key || "");
      parent.addEventListener("change", function () {
        item.parent_key = parent.value || null;
        render();
      });
      function offsetInput(current, assign) {
        var node = document.createElement("input");
        node.type = "number";
        node.min = "0";
        node.value = current == null ? "" : String(current);
        node.addEventListener("input", function () {
          assign(node.value === "" ? null : Number(node.value));
          write();
        });
        return node;
      }
      function timeInput(minute, assign) {
        var node = document.createElement("input");
        node.type = "time";
        if (minute != null) {
          var hours = String(Math.floor(minute / 60)).padStart(2, "0");
          var minutes = String(minute % 60).padStart(2, "0");
          node.value = hours + ":" + minutes;
        }
        node.addEventListener("input", function () {
          if (!node.value) {
            assign(null);
          } else {
            var parts = node.value.split(":");
            assign(Number(parts[0]) * 60 + Number(parts[1]));
          }
          write();
        });
        return node;
      }
      var remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "Remove item";
      remove.addEventListener("click", function () {
        var removedKey = keyOf(item);
        items = items.filter(function (row) {
          return keyOf(row) !== removedKey;
        });
        items.forEach(function (row) {
          if (row.parent_key === removedKey) {
            row.parent_key = item.parent_key || null;
          }
        });
        render();
      });
      card.appendChild(field("Title", title));
      card.appendChild(field("Type", type));
      card.appendChild(field("Parent", parent));
      card.appendChild(field("Default description", description));
      card.appendChild(field("Priority", priority));
      card.appendChild(field("Labels", labels));
      card.appendChild(field("Assignee", assignee));
      card.appendChild(field("Start offset (days before)", offsetInput(item.start_offset_days, function (value) {
        item.start_offset_days = value;
      })));
      card.appendChild(field("Start time", timeInput(item.start_minute_of_day, function (value) {
        item.start_minute_of_day = value;
      })));
      card.appendChild(field("Due offset (days after)", offsetInput(item.due_offset_days, function (value) {
        item.due_offset_days = value;
      })));
      card.appendChild(field("Due time", timeInput(item.due_minute_of_day, function (value) {
        item.due_minute_of_day = value;
      })));
      card.appendChild(remove);
      root.appendChild(card);
      void index;
    });
    write();
  }

  var add = document.querySelector("[data-series-items-add]");
  if (add) {
    add.addEventListener("click", function () {
      items.push({
        key: "new:" + nextKey++,
        parent_key: null,
        title: "",
        description: "",
        type: "story",
        priority: "p4",
        labels: [],
        assignee_id: null,
        start_offset_days: null,
        start_minute_of_day: null,
        due_offset_days: null,
        due_minute_of_day: null,
      });
      render();
      var titles = root.querySelectorAll("input[type=text]");
      if (titles.length) {
        titles[titles.length - 1].focus();
      }
    });
  }
  render();
})();
