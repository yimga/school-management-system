(function () {
  "use strict";

  var contractNode = document.getElementById("rmcAdminNavigationContract");
  var roots = Array.prototype.slice.call(document.querySelectorAll('[data-rmc-admin-sidebar-v3="1"]'));
  if (!contractNode || !roots.length) return;

  var contract;
  try { contract = JSON.parse(contractNode.textContent || "{}"); }
  catch (_error) { return; }
  if (!contract || contract.version !== 3 || !contract.scope) return;

  function copy(key, fallback) { return String((contract.strings || {})[key] || fallback); }

  var queueKey = "rmc-admin-navigation-ops-v3:" + contract.scope;
  var channel = "BroadcastChannel" in window ? new BroadcastChannel("rmc-admin-navigation-v3:" + contract.scope) : null;
  var revision = Number(contract.revision || 0);
  var authoritativeState = normalizeState(contract.preferences);
  var state = normalizeState(authoritativeState);
  var queue = readQueue();
  var draining = false;
  var stalled = false;
  var retryTimer = null;
  var lastUndo = null;
  var dialog = null;
  var commandLinks = [];
  var commandActiveIndex = -1;
  var drawerReturnFocus = null;
  var registry = new Map();
  (contract.destinations || []).forEach(function (item) { if (item && item.id) registry.set(item.id, item); });
  if (contract.page && contract.page.destination_id && contract.page.path) {
    registry.set(contract.page.destination_id, {
      id: contract.page.destination_id,
      label: contract.page.title || document.title,
      path: contract.page.path,
      group: "Current page",
      kind: contract.page.object_id ? "record" : "page",
      keywords: []
    });
  }

  function normalizeState(value) {
    value = value && typeof value === "object" ? value : {};
    return {
      pinned: Array.isArray(value.pinned) ? value.pinned.slice(0, Number((contract.limits || {}).pinned || 8)) : [],
      recent: Array.isArray(value.recent) ? value.recent.slice(0, Number((contract.limits || {}).recent || 10)) : [],
      mode: value.mode === "compact" ? "compact" : "expanded",
      focus: value.focus === true,
      expansions: value.expansions && typeof value.expansions === "object" ? Object.assign({}, value.expansions) : {},
      dismissedRecommendations: Array.isArray(value.dismissedRecommendations) ? value.dismissedRecommendations.slice() : []
    };
  }

  function readQueue() {
    try {
      var value = JSON.parse(localStorage.getItem(queueKey) || "[]");
      return Array.isArray(value) ? value.filter(validOperation).slice(-100) : [];
    } catch (_error) { return []; }
  }

  function writeQueue() {
    try { localStorage.setItem(queueKey, JSON.stringify(queue)); } catch (_error) { /* storage is an optional retry aid */ }
  }

  function validOperation(operation) {
    return operation && typeof operation.id === "string" && typeof operation.type === "string" && operation.payload && typeof operation.payload === "object";
  }

  function mutationId() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") return "nav:" + window.crypto.randomUUID();
    return "nav:" + Date.now().toString(36) + ":" + Math.random().toString(36).slice(2, 12);
  }

  // CSRF for the preference writes below. Read the DOM FIRST, then both cookie
  // names. Until 2026-09-06 this read only a cookie literally named
  // "csrftoken", and the regex requires start-of-string or "; " before the
  // name -- so on the manager host, where ManagerCookieIsolationMiddleware
  // issues "rmc_manager_csrftoken" instead, it matched nothing and returned "".
  // An EMPTY header is not a missing one: Django rejects it with
  // "CSRF token from the 'X-Csrftoken' HTTP header has incorrect length"
  // (a valid token is 32 or 64 chars). Every PATCH to
  // /admin/navigation-preferences/ 403'd, so no operator's sidebar state ever
  // saved on the manager host -- silently, because the only symptom is a
  // console error on a fire-and-forget fetch. Measured in a real browser:
  // 8 admin page loads, 8 403s.
  // The rendered csrfmiddlewaretoken input and <meta name="csrf-token"> are
  // host-independent and survive CSRF_COOKIE_HTTPONLY=True, so they come first.
  function csrfToken() {
    var input = document.querySelector('input[name=csrfmiddlewaretoken]');
    if (input && input.value) return input.value;
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content && meta.content !== "NOTPROVIDED") return meta.content;
    var names = ["csrftoken", "rmc_manager_csrftoken"];
    var cookie = document.cookie || "";
    for (var i = 0; i < names.length; i++) {
      var match = cookie.match(new RegExp("(?:^|;\s*)" + names[i] + "=([^;]+)"));
      if (match) return decodeURIComponent(match[1]);
    }
    return "";
  }

  function entryFor(destinationId) {
    var destination = registry.get(destinationId);
    return destination ? { id: destination.id, path: destination.path, label: destination.label } : null;
  }

  function destinationPayload(destinationId) {
    var payload = { destinationId: destinationId };
    if (contract.page && contract.page.destination_id === destinationId && contract.page.pinToken) payload.destinationToken = contract.page.pinToken;
    return payload;
  }

  function applyLocal(target, operation) {
    var next = normalizeState(target);
    var payload = operation.payload || {};
    var destinationId = String(payload.destinationId || "");
    var entry;
    if (operation.type === "pin" || operation.type === "remember_recent") {
      entry = entryFor(destinationId);
      if (!entry) return next;
      var key = operation.type === "pin" ? "pinned" : "recent";
      var list = next[key].filter(function (item) { return item && item.id !== destinationId; });
      if (key === "recent") list.unshift(entry); else list.push(entry);
      next[key] = list.slice(0, Number((contract.limits || {})[key] || (key === "pinned" ? 8 : 10)));
    } else if (operation.type === "unpin") {
      next.pinned = next.pinned.filter(function (item) { return item && item.id !== destinationId; });
    } else if (operation.type === "move_pin") {
      var current = next.pinned.findIndex(function (item) { return item && item.id === destinationId; });
      if (current >= 0) {
        entry = next.pinned.splice(current, 1)[0];
        var index = Math.max(0, Math.min(Number(payload.index || 0), next.pinned.length));
        next.pinned.splice(index, 0, entry);
      }
    } else if (operation.type === "clear_recent") {
      next.recent = [];
    } else if (operation.type === "set_mode") {
      next.mode = payload.mode === "compact" ? "compact" : "expanded";
    } else if (operation.type === "set_focus") {
      next.focus = payload.enabled === true;
    } else if (operation.type === "set_expansion") {
      next.expansions[String(payload.key || "")] = payload.expanded === true;
    } else if (operation.type === "dismiss_recommendation") {
      var recommendationId = String(payload.recommendationId || "");
      next.dismissedRecommendations = next.dismissedRecommendations.filter(function (id) { return id !== recommendationId; });
      next.dismissedRecommendations.push(recommendationId);
    } else if (operation.type === "reset") {
      return normalizeState({});
    }
    return next;
  }

  function optimisticState(base) {
    return queue.reduce(function (current, operation) { return applyLocal(current, operation); }, normalizeState(base));
  }

  function setSync(label, status) {
    roots.forEach(function (root) {
      var holder = root.querySelector("[data-rmc-admin-sync]");
      var copy = root.querySelector("[data-rmc-admin-sync-label]");
      if (holder) holder.setAttribute("data-status", status || "ready");
      if (copy) copy.textContent = label;
      var retry = root.querySelector("[data-rmc-admin-retry]");
      if (retry) retry.hidden = status !== "error" || !queue.length;
    });
  }

  function emitTelemetry(eventName, detail) {
    var safe = Object.assign({
      event: eventName,
      scope: contract.hostKind,
      adminSite: contract.adminSite,
      revision: revision,
      queued: queue.length
    }, detail || {});
    window.dispatchEvent(new CustomEvent("rmc:admin-navigation-telemetry", { detail: safe }));
  }

  function enqueue(type, payload, undo) {
    var operation = { id: mutationId(), type: type, payload: payload || {}, baseRevision: revision, attempts: 0 };
    queue.push(operation);
    stalled = false;
    state = applyLocal(state, operation);
    writeQueue();
    if (undo) showUndo(undo);
    render();
    drain();
  }

  function drain() {
    if (draining || stalled || !queue.length || !contract.endpoint) return;
    if (navigator.onLine === false) {
      setSync((contract.strings || {}).offlineReady || "Offline changes queued", "offline");
      return;
    }
    window.clearTimeout(retryTimer);
    draining = true;
    setSync((contract.strings || {}).syncing || "Saving navigation", "syncing");
    var operation = queue[0];
    var startedAt = performance.now();
    fetch(contract.endpoint, {
      method: "PATCH",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ expected_revision: revision, mutation: { id: operation.id, type: operation.type, payload: operation.payload } })
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) { return { response: response, data: data }; });
    }).then(function (result) {
      if (result.response.status === 409 && result.data.code === "revision_conflict") {
        revision = Number(result.data.revision || revision);
        authoritativeState = normalizeState(result.data.preferences || {});
        state = optimisticState(authoritativeState);
        operation.attempts = Number(operation.attempts || 0) + 1;
        writeQueue();
        setSync((contract.strings || {}).conflict || "Rebasing navigation", "conflict");
        emitTelemetry("revision_conflict", { mutationType: operation.type, attempt: operation.attempts, latencyMs: Math.round(performance.now() - startedAt) });
        if (operation.attempts >= 3) stalled = true;
        return;
      }
      if (!result.response.ok || result.data.ok !== true) {
        if (result.response.status >= 400 && result.response.status < 500) {
          queue.shift();
          writeQueue();
          state = optimisticState(authoritativeState);
          stalled = false;
          setSync(result.data.error || (contract.strings || {}).saveFailed || "Navigation could not be saved", "error");
          emitTelemetry("mutation_rejected", { mutationType: operation.type, status: result.response.status, code: result.data.code || "invalid_request", latencyMs: Math.round(performance.now() - startedAt) });
          return;
        }
        var failure = new Error(result.data.error || "Navigation mutation failed");
        failure.status = result.response.status;
        throw failure;
      }
      revision = Number(result.data.revision || revision + 1);
      queue.shift();
      authoritativeState = normalizeState(result.data.preferences || {});
      state = optimisticState(authoritativeState);
      writeQueue();
      stalled = false;
      emitTelemetry("mutation_committed", { mutationType: operation.type, latencyMs: Math.round(performance.now() - startedAt) });
      if (channel) channel.postMessage({ type: "committed", revision: revision });
    }).catch(function (error) {
      operation.attempts = Number(operation.attempts || 0) + 1;
      stalled = operation.attempts >= 5;
      writeQueue();
      setSync((contract.strings || {}).saveFailed || "Navigation could not be saved", "error");
      emitTelemetry("mutation_retry", { mutationType: operation.type, attempt: operation.attempts, status: Number(error.status || 0), latencyMs: Math.round(performance.now() - startedAt) });
    }).finally(function () {
      draining = false;
      render();
      if (queue.length && navigator.onLine !== false && !stalled) {
        var delay = Math.min(30000, 250 * Math.pow(2, Number(queue[0].attempts || 0)));
        retryTimer = window.setTimeout(drain, delay);
      }
    });
  }

  function refreshFromServer() {
    if (!contract.endpoint || navigator.onLine === false || draining) return;
    fetch(contract.endpoint, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (response) { if (!response.ok) throw new Error("read failed"); return response.json(); })
      .then(function (data) {
        if (data.ok !== true) return;
        revision = Number(data.revision || revision);
        authoritativeState = normalizeState(data.preferences || {});
        state = optimisticState(authoritativeState);
        render();
      }).catch(function () { /* another online event will retry */ });
  }

  function createSavedItem(entry, index, kind) {
    var item = document.createElement("li");
    var link = document.createElement("a");
    link.href = entry.path;
    link.textContent = entry.label;
    item.appendChild(link);
    if (kind === "pinned") {
      var controls = document.createElement("span");
      controls.className = "rmc-admin-sidebar-v3__saved-actions";
      [["↑", index - 1, copy("movePinUp", "Move pin up")], ["↓", index + 1, copy("movePinDown", "Move pin down")]].forEach(function (specification) {
        var move = document.createElement("button");
        move.type = "button"; move.textContent = specification[0]; move.title = specification[2]; move.setAttribute("aria-label", specification[2]);
        move.disabled = specification[1] < 0 || specification[1] >= state.pinned.length;
        move.addEventListener("click", function () { enqueue("move_pin", { destinationId: entry.id, index: specification[1] }); });
        controls.appendChild(move);
      });
      var remove = document.createElement("button");
      remove.type = "button"; remove.textContent = "×"; remove.title = copy("removePin", "Remove pin"); remove.setAttribute("aria-label", copy("removePin", "Remove pin"));
      remove.addEventListener("click", function () { enqueue("unpin", { destinationId: entry.id }, { type: "pin", payload: destinationPayload(entry.id), label: "Pin removed" }); });
      controls.appendChild(remove); item.appendChild(controls);
    }
    return item;
  }

  function renderRoot(root) {
    var pinnedList = root.querySelector("[data-rmc-admin-pinned-list]");
    var recentList = root.querySelector("[data-rmc-admin-recent-list]");
    if (pinnedList) {
      pinnedList.textContent = "";
      state.pinned.forEach(function (entry, index) { pinnedList.appendChild(createSavedItem(entry, index, "pinned")); });
    }
    if (recentList) {
      recentList.textContent = "";
      state.recent.forEach(function (entry, index) {
        if (!contract.page || entry.id !== contract.page.destination_id) recentList.appendChild(createSavedItem(entry, index, "recent"));
      });
    }
    var count = root.querySelector("[data-rmc-admin-pinned-count]");
    if (count) count.textContent = String(state.pinned.length);
    var empty = root.querySelector("[data-rmc-admin-pinned-empty]");
    if (empty) empty.hidden = state.pinned.length > 0;
    var recentWrap = root.querySelector("[data-rmc-admin-recent-wrap]");
    if (recentWrap) recentWrap.hidden = state.recent.filter(function (entry) { return !contract.page || entry.id !== contract.page.destination_id; }).length === 0;
    var pinCurrent = root.querySelector("[data-rmc-admin-pin-current]");
    if (pinCurrent && contract.page) {
      var pinned = state.pinned.some(function (entry) { return entry.id === contract.page.destination_id; });
      pinCurrent.setAttribute("aria-pressed", pinned ? "true" : "false");
      var pinLabel = pinCurrent.querySelector("span:last-child");
      if (pinLabel) pinLabel.textContent = pinned ? copy("unpinThisPage", "Unpin this page") : copy("pinThisPage", "Pin this page");
    }
    var focus = root.querySelector("[data-rmc-admin-focus]");
    if (focus) focus.setAttribute("aria-pressed", state.focus ? "true" : "false");
    var mode = root.querySelector("[data-rmc-admin-mode]");
    if (mode) mode.setAttribute("aria-pressed", state.mode === "compact" ? "true" : "false");
    var modeLabel = root.querySelector("[data-rmc-admin-mode-label]");
    if (modeLabel) modeLabel.textContent = state.mode === "compact" ? copy("expanded", "Expanded") : copy("compact", "Compact");
    root.querySelectorAll("[data-rmc-recommendation-id]").forEach(function (node) {
      node.hidden = state.dismissedRecommendations.indexOf(node.getAttribute("data-rmc-recommendation-id")) >= 0;
    });
    var now = root.querySelector("[data-rmc-admin-now]");
    if (now) now.hidden = !now.querySelector('[data-rmc-recommendation-id]:not([hidden])');
  }

  function render() {
    document.body.classList.toggle("rmc-admin-sidebar-compact-v3", state.mode === "compact");
    document.body.classList.toggle("rmc-admin-sidebar-focus-v3", state.focus);
    roots.forEach(renderRoot);
    if (!draining) {
      if (stalled) setSync((contract.strings || {}).saveFailed || "Navigation could not be saved", "error");
      else if (navigator.onLine === false || queue.length) setSync((contract.strings || {}).offlineReady || "Offline changes queued", "offline");
      else setSync((contract.strings || {}).localReady || "Local ready", "ready");
    }
  }

  function showUndo(inverse) {
    lastUndo = inverse;
    roots.forEach(function (root) {
      var box = root.querySelector("[data-rmc-admin-undo]");
      var label = root.querySelector("[data-rmc-admin-undo-label]");
      if (box) box.hidden = false;
      if (label) label.textContent = inverse.label || "Navigation updated";
    });
    window.clearTimeout(showUndo.timer);
    showUndo.timer = window.setTimeout(function () {
      lastUndo = null;
      roots.forEach(function (root) { var box = root.querySelector("[data-rmc-admin-undo]"); if (box) box.hidden = true; });
    }, 7000);
  }

  function commandDialog() {
    if (dialog) return dialog;
    dialog = document.createElement("dialog");
    dialog.className = "rmc-admin-command-v3";
    dialog.setAttribute("aria-labelledby", "rmcAdminCommandTitle");
    dialog.innerHTML = '<form method="dialog" class="rmc-admin-command-v3__frame"><header><div><strong id="rmcAdminCommandTitle"></strong><span data-rmc-command-subtitle></span></div><button value="close" aria-label="Close command palette">×</button></header><label><span class="visually-hidden">Search admin destinations</span><input type="search" data-rmc-admin-command-query autocomplete="off"></label><div data-rmc-admin-command-results></div><footer><span>↑↓ move</span><span>Enter open</span><span>Esc close</span></footer></form>';
    dialog.querySelector("#rmcAdminCommandTitle").textContent = copy("commandTitle", "Admin command palette");
    dialog.querySelector("[data-rmc-command-subtitle]").textContent = copy("commandSubtitle", "Permission-aware pages, records and actions");
    dialog.querySelector("[data-rmc-admin-command-query]").placeholder = copy("searchPlaceholder", "Search pages, records and actions…");
    document.body.appendChild(dialog);
    var input = dialog.querySelector("[data-rmc-admin-command-query]");
    input.addEventListener("input", function () { renderCommand(input.value); });
    dialog.addEventListener("keydown", function (event) {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        moveCommandSelection(event.key === "ArrowDown" ? 1 : -1);
      } else if (event.key === "Enter" && event.target === input && commandLinks[commandActiveIndex]) {
        event.preventDefault();
        commandLinks[commandActiveIndex].click();
      }
    });
    dialog.addEventListener("click", function (event) { if (event.target === dialog) dialog.close(); });
    return dialog;
  }

  function renderCommand(query) {
    var holder = commandDialog().querySelector("[data-rmc-admin-command-results]");
    var terms = String(query || "").toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    var currentGroup = contract.page && contract.page.app_label;
    var items = Array.from(registry.values()).filter(function (item) {
      var haystack = [item.label, item.group, item.kind].concat(item.keywords || []).join(" ").toLocaleLowerCase();
      return terms.every(function (term) { return haystack.indexOf(term) >= 0; });
    }).map(function (item) {
      var label = String(item.label || "").toLocaleLowerCase();
      var joined = terms.join(" ");
      var score = !terms.length ? 0 : (label === joined ? 1000 : (label.indexOf(joined) === 0 ? 650 : 300));
      if (currentGroup && String(item.id).indexOf(":" + currentGroup + ":") >= 0) score += 140;
      if (state.pinned.some(function (entry) { return entry.id === item.id; })) score += 100;
      var recentIndex = state.recent.findIndex(function (entry) { return entry.id === item.id; });
      if (recentIndex >= 0) score += Math.max(10, 80 - recentIndex * 6);
      if (item.kind === "action") score += 20;
      return { item: item, score: score };
    }).sort(function (left, right) {
      return right.score - left.score || String(left.item.label).localeCompare(String(right.item.label));
    }).map(function (ranked) { return ranked.item; });
    holder.textContent = "";
    commandLinks = [];
    commandActiveIndex = -1;
    if (!items.length) { var empty = document.createElement("p"); empty.textContent = (contract.strings || {}).noResults || "No permitted destinations match your search."; holder.appendChild(empty); return; }
    [
      { label: copy("actions", "Actions"), kinds: ["action"] },
      { label: copy("records", "Records"), kinds: ["record"] },
      { label: copy("pages", "Pages"), kinds: ["page", "model", "app", "home", "destination"] }
    ].forEach(function (group) {
      var matching = items.filter(function (item) { return group.kinds.indexOf(item.kind) >= 0; });
      if (!matching.length) return;
      var section = document.createElement("section");
      var heading = document.createElement("h2"); heading.textContent = group.label; section.appendChild(heading);
      matching.slice(0, 12).forEach(function (item) {
        var row = document.createElement("div");
        var link = document.createElement("a"); link.href = item.path; link.innerHTML = "<strong></strong><span></span><em></em>"; link.querySelector("strong").textContent = item.label; link.querySelector("span").textContent = item.description || item.group || ""; link.querySelector("em").textContent = copy("scope", "Scope") + ": " + (item.scope || contract.hostKind || contract.adminSite || "admin"); link.setAttribute("data-rmc-command-result", "1"); row.appendChild(link);
        var pin = document.createElement("button"); pin.type = "button"; pin.textContent = state.pinned.some(function (entry) { return entry.id === item.id; }) ? copy("unpin", "Unpin") : copy("pin", "Pin");
        pin.addEventListener("click", function () { var isPinned = state.pinned.some(function (entry) { return entry.id === item.id; }); enqueue(isPinned ? "unpin" : "pin", destinationPayload(item.id), { type: isPinned ? "pin" : "unpin", payload: destinationPayload(item.id), label: isPinned ? "Pin removed" : "Page pinned" }); renderCommand(query); });
        row.appendChild(pin); section.appendChild(row);
      });
      holder.appendChild(section);
    });
    commandLinks = Array.prototype.slice.call(holder.querySelectorAll("[data-rmc-command-result]"));
    if (commandLinks.length) {
      commandActiveIndex = 0;
      commandLinks.forEach(function (link, index) { link.tabIndex = index === 0 ? 0 : -1; });
    }
  }

  function moveCommandSelection(delta) {
    if (!commandLinks.length) return;
    commandActiveIndex = (commandActiveIndex + delta + commandLinks.length) % commandLinks.length;
    commandLinks.forEach(function (link, index) { link.tabIndex = index === commandActiveIndex ? 0 : -1; });
    commandLinks[commandActiveIndex].focus();
  }

  function openCommands() {
    var current = commandDialog();
    renderCommand("");
    if (typeof current.showModal === "function") current.showModal();
    else current.setAttribute("open", "");
    window.setTimeout(function () { var input = current.querySelector("[data-rmc-admin-command-query]"); if (input) input.focus(); }, 0);
  }

  function setDrawer(open, trigger, restoreFocus) {
    var shell = document.querySelector('[data-rmc-shell-root="django-admin"]');
    if (!shell) return;
    var sidebar = shell.querySelector("#rmc-admin-sidebar-drawer");
    var toggle = trigger || shell.querySelector("[data-rmc-admin-drawer-toggle]");
    var canvas = shell.querySelector('[data-rmc-shell-canvas="django-admin"]');
    if (open) drawerReturnFocus = toggle || document.activeElement;
    shell.setAttribute("data-rmc-shell-sidebar-open", open ? "true" : "false");
    if (toggle) {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.setAttribute("aria-label", open ? "Close admin navigation" : "Open admin navigation");
    }
    if (canvas) canvas.inert = open;
    if (open && sidebar) {
      window.setTimeout(function () {
        var first = sidebar.querySelector('button:not([disabled]), a[href], summary, input:not([disabled])');
        if (first) first.focus();
      }, 0);
    } else if (restoreFocus !== false && drawerReturnFocus && typeof drawerReturnFocus.focus === "function") {
      drawerReturnFocus.focus();
    }
  }

  document.addEventListener("click", function (event) {
    var openShell = document.querySelector('[data-rmc-shell-root="django-admin"][data-rmc-shell-sidebar-open="true"]');
    if (openShell && !event.target.closest("#rmc-admin-sidebar-drawer") && !event.target.closest("[data-rmc-admin-drawer-toggle]")) setDrawer(false, null, false);
    var target = event.target.closest("button");
    if (!target) return;
    if (target.matches("[data-rmc-admin-drawer-toggle]")) {
      var shell = target.closest('[data-rmc-shell-root="django-admin"]');
      if (shell) {
        var open = shell.getAttribute("data-rmc-shell-sidebar-open") !== "true";
        setDrawer(open, target, true);
      }
    } else if (target.matches("[data-rmc-admin-command-open]")) openCommands();
    else if (target.matches("[data-rmc-admin-retry]")) {
      queue.forEach(function (operation) { operation.attempts = 0; });
      stalled = false;
      writeQueue();
      refreshFromServer();
      drain();
    }
    else if (target.matches("[data-rmc-admin-focus]")) enqueue("set_focus", { enabled: !state.focus }, { type: "set_focus", payload: { enabled: state.focus }, label: state.focus ? "Focus disabled" : "Focus enabled" });
    else if (target.matches("[data-rmc-admin-mode]")) enqueue("set_mode", { mode: state.mode === "compact" ? "expanded" : "compact" }, { type: "set_mode", payload: { mode: state.mode }, label: "Sidebar mode changed" });
    else if (target.matches("[data-rmc-admin-reset]")) {
      if (window.confirm(copy("resetConfirm", "Reset your navigation preferences for this admin workspace? No records or permissions will be changed."))) enqueue("reset", {});
    }
    else if (target.matches("[data-rmc-admin-pin-current]") && contract.page) {
      var pinned = state.pinned.some(function (entry) { return entry.id === contract.page.destination_id; });
      enqueue(pinned ? "unpin" : "pin", destinationPayload(contract.page.destination_id), { type: pinned ? "pin" : "unpin", payload: destinationPayload(contract.page.destination_id), label: pinned ? "Pin removed" : "Page pinned" });
    } else if (target.matches("[data-rmc-admin-recent-clear]")) enqueue("clear_recent", {});
    else if (target.matches("[data-rmc-admin-dismiss-recommendation]")) enqueue("dismiss_recommendation", { recommendationId: target.getAttribute("data-rmc-admin-dismiss-recommendation") });
    else if (target.matches("[data-rmc-admin-undo-action]") && lastUndo) { var inverse = lastUndo; lastUndo = null; enqueue(inverse.type, inverse.payload); }
  });

  document.addEventListener("toggle", function (event) {
    var details = event.target.closest && event.target.closest("[data-rmc-admin-models]");
    if (details && event.target === details) enqueue("set_expansion", { key: "models", expanded: details.open });
  }, true);

  document.addEventListener("keydown", function (event) {
    var editable = /input|textarea|select/i.test((event.target && event.target.tagName) || "") || (event.target && event.target.isContentEditable);
    if (event.key === "Escape") {
      var shell = document.querySelector('[data-rmc-shell-root="django-admin"]');
      if (shell && shell.getAttribute("data-rmc-shell-sidebar-open") === "true") {
        setDrawer(false, null, true);
      }
    }
    if (event.key === "Tab") {
      var openShell = document.querySelector('[data-rmc-shell-root="django-admin"][data-rmc-shell-sidebar-open="true"]');
      var sidebar = openShell && openShell.querySelector("#rmc-admin-sidebar-drawer");
      if (sidebar && window.matchMedia("(max-width: 1024px)").matches) {
        var focusable = Array.prototype.slice.call(sidebar.querySelectorAll('button:not([disabled]), a[href], summary, input:not([disabled]), [tabindex]:not([tabindex="-1"])')).filter(function (node) { return node.offsetParent !== null; });
        if (focusable.length) {
          var first = focusable[0]; var last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      }
    }
    if (((event.ctrlKey || event.metaKey) && event.key.toLocaleLowerCase() === "k") || (!editable && event.key === "/")) { event.preventDefault(); openCommands(); }
  });

  window.addEventListener("online", function () { stalled = false; refreshFromServer(); drain(); });
  window.addEventListener("offline", render);
  window.addEventListener("storage", function (event) { if (event.key === queueKey) { queue = readQueue(); state = optimisticState(authoritativeState); render(); refreshFromServer(); drain(); } });
  window.addEventListener("resize", function () { if (!window.matchMedia("(max-width: 1024px)").matches) setDrawer(false, null, false); });
  if (channel) channel.addEventListener("message", function (event) { if (event.data && Number(event.data.revision || 0) > revision) refreshFromServer(); });

  if (state.expansions.models === true) roots.forEach(function (root) { var details = root.querySelector("[data-rmc-admin-models]"); if (details) details.open = true; });
  state = optimisticState(authoritativeState);
  render();
  if (contract.page && contract.page.destination_id && !state.recent.some(function (entry) { return entry.id === contract.page.destination_id; })) enqueue("remember_recent", destinationPayload(contract.page.destination_id));
  else drain();
})();
