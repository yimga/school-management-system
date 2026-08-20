(function () {
  "use strict";

  var DEFAULT_STATE = {
    pinned: [], recent: [], compact: false, advancedOpen: false, appsOpen: false,
  };
  var contract = readContract();
  var limits = Object.assign({ pinned: 8, recent: 10 }, contract.limits || {});
  var state = sanitizeState(contract.preferences || DEFAULT_STATE);
  var pendingKey = "rmc-admin-navigation-pending-v1:" + (contract.scope || "unavailable");
  var pending = safeRead(pendingKey, null);
  if (pending) state = sanitizeState(pending);

  function readContract() {
    var node = document.getElementById("rmcAdminNavigationContract");
    if (!node) return {};
    try {
      var parsed = JSON.parse(node.textContent || "{}");
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch (_error) { return {}; }
  }

  function safeRead(key, fallback) {
    try {
      var value = JSON.parse(localStorage.getItem(key) || "null");
      return value === null ? fallback : value;
    } catch (_error) { return fallback; }
  }

  function safeWrite(key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, JSON.stringify(value));
    } catch (_error) {
      /* The edge database remains authoritative when browser storage is absent. */
    }
  }

  function text(value) { return String(value || "").replace(/\s+/g, " ").trim(); }

  function adminPath(value) {
    try {
      var url = new URL(String(value || ""), window.location.origin);
      if (url.origin !== window.location.origin || !url.pathname.startsWith("/admin/")) return "";
      return url.pathname + url.search;
    } catch (_error) { return ""; }
  }

  function sanitizeEntries(value, limit) {
    var result = [], seen = {};
    if (!Array.isArray(value)) return result;
    value.slice(0, limit).forEach(function (row) {
      var path = row && adminPath(row.path), label = text(row && row.label).slice(0, 100);
      if (!path || !label || seen[path]) return;
      seen[path] = true;
      result.push({ path: path, label: label });
    });
    return result;
  }

  function sanitizeState(value) {
    value = value && typeof value === "object" && !Array.isArray(value) ? value : {};
    return {
      pinned: sanitizeEntries(value.pinned, limits.pinned),
      recent: sanitizeEntries(value.recent, limits.recent),
      compact: value.compact === true,
      advancedOpen: value.advancedOpen === true,
      appsOpen: value.appsOpen === true,
    };
  }

  function csrfToken() {
    var match = (document.cookie || "").match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function announce(message) {
    var output = document.getElementById("admin-sidebar-live");
    if (!output) return;
    output.textContent = "";
    window.setTimeout(function () { output.textContent = message || ""; }, 30);
  }

  function persist(patch) {
    state = sanitizeState(Object.assign({}, state, patch || {}));
    safeWrite(pendingKey, state);
    if (!contract.endpoint || navigator.onLine === false) return Promise.resolve(false);
    return fetch(contract.endpoint, {
      method: "POST", credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
      body: JSON.stringify({ preferences: state }),
    }).then(function (response) {
      if (!response.ok) throw new Error("Navigation preference save failed");
      return response.json();
    }).then(function (payload) {
      if (!payload.ok) throw new Error(payload.error || "Navigation preference save failed");
      state = sanitizeState(payload.preferences);
      safeWrite(pendingKey, null);
      return true;
    }).catch(function () {
      announce("Changes are saved on this device and will sync when the connection returns.");
      return false;
    });
  }

  window.announceAdminSidebar = announce;
  window.getQuickAccessState = function () {
    return { startOpen: true, setupOpen: true, setupAdvancedOpen: state.advancedOpen, librariesOpen: false };
  };
  window.getAdminAppsState = function (hasCurrentApp) { return Boolean(hasCurrentApp || state.appsOpen); };
  window.rmcTenantAdminNavigationChanged = function (patch) { persist(patch || {}); };

  function focusables(sidebar) {
    return Array.prototype.filter.call(
      sidebar.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),[tabindex="0"]'),
      function (node) { return node.offsetParent !== null && !node.closest('[data-rmc-admin-search-hidden="1"]'); }
    );
  }

  function entryNode(row, removable) {
    var item = document.createElement("li"), link = document.createElement("a");
    var icon = document.createElement("span"), label = document.createElement("span");
    link.href = row.path;
    link.className = removable ? "admin-sidebar-link admin-sidebar-pinned-link flex-grow-1 text-truncate" : "rmc-tenant-admin-recent-link";
    icon.className = "rmc-tenant-admin-history-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l3 2"/></svg>';
    label.textContent = row.label;
    link.appendChild(icon); link.appendChild(label); item.appendChild(link);
    if (removable) {
      item.className = "admin-sidebar-pinned-item d-flex align-items-center gap-1";
      var button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-link btn-sm p-0 text-muted admin-unpin";
      button.setAttribute("aria-label", "Unpin " + row.label);
      button.dataset.path = row.path;
      button.textContent = "×";
      item.appendChild(button);
    }
    return item;
  }

  function renderPinned(sidebar) {
    var list = sidebar.querySelector("#admin-sidebar-pinned-list");
    var count = sidebar.querySelector("[data-rmc-pinned-count]");
    var empty = sidebar.querySelector("[data-rmc-pinned-empty]");
    var button = sidebar.querySelector("#admin-pin-this-page");
    if (!list) return;
    sidebar.querySelectorAll('[data-rmc-admin-pin-replaced="1"]').forEach(function (link) {
      link.hidden = false;
      link.removeAttribute("data-rmc-admin-pin-replaced");
    });
    list.replaceChildren();
    state.pinned.forEach(function (row) {
      list.appendChild(entryNode(row, true));
      sidebar.querySelectorAll("a[href]").forEach(function (link) {
        if (link.closest("[data-rmc-admin-recent-wrap], #admin-sidebar-pinned-wrap")) return;
        if (adminPath(link.getAttribute("href")) !== row.path) return;
        link.hidden = true;
        link.setAttribute("data-rmc-admin-pin-replaced", "1");
      });
    });
    if (count) count.textContent = String(state.pinned.length);
    if (empty) empty.hidden = state.pinned.length > 0;
    if (button) {
      var path = window.location.pathname + window.location.search;
      var alreadyPinned = state.pinned.some(function (row) { return row.path === path; });
      button.disabled = alreadyPinned;
      button.setAttribute("aria-pressed", alreadyPinned ? "true" : "false");
      button.title = alreadyPinned ? "This page is already pinned" : "Add this page to your Pinned list above";
    }
  }

  function renderRecent(sidebar) {
    var wrap = sidebar.querySelector("[data-rmc-admin-recent-wrap]");
    var list = sidebar.querySelector("[data-rmc-admin-recent-list]");
    if (!wrap || !list) return;
    var current = window.location.pathname + window.location.search;
    var canonical = {};
    sidebar.querySelectorAll("a[href]").forEach(function (link) {
      if (link.closest("[data-rmc-admin-recent-wrap], #admin-sidebar-pinned-wrap")) return;
      var path = adminPath(link.getAttribute("href"));
      if (path) canonical[path] = true;
    });
    var rows = state.recent.filter(function (row) {
      return row.path !== current && !canonical[row.path];
    });
    list.replaceChildren();
    rows.forEach(function (row) { list.appendChild(entryNode(row, false)); });
    wrap.hidden = rows.length === 0;
  }

  function rememberCurrent(sidebar) {
    var path = window.location.pathname + window.location.search;
    if (!path.startsWith("/admin/") || path === "/admin/") return;
    var heading = document.querySelector("main h1, #content h1, h1");
    var label = text(heading && heading.textContent) || text(document.title) || path;
    if (
      state.recent.length &&
      state.recent[0].path === path &&
      state.recent[0].label === label.slice(0, 100)
    ) {
      renderRecent(sidebar);
      return;
    }
    var recent = state.recent.filter(function (row) { return row.path !== path; });
    recent.unshift({ path: path, label: label.slice(0, 100) });
    state.recent = recent.slice(0, limits.recent);
    renderRecent(sidebar);
    persist({ recent: state.recent });
  }

  function filter(sidebar, query) {
    var value = text(query).toLocaleLowerCase();
    var terms = value.split(/\s+/).filter(Boolean), matches = 0;
    sidebar.querySelectorAll("#nav-sidebar-apps a[href]").forEach(function (link) {
      var haystack = text(link.textContent + " " + (link.getAttribute("data-admin-search") || "")).toLocaleLowerCase();
      var hit = !terms.length || terms.every(function (term) { return haystack.includes(term); });
      link.toggleAttribute("data-rmc-admin-search-match", Boolean(value && hit));
      var item = link.closest("li") || link;
      item.toggleAttribute("data-rmc-admin-search-hidden", !hit);
      if (hit && value) matches += 1;
    });
    sidebar.toggleAttribute("data-rmc-admin-nav-filtered", Boolean(value));
    sidebar.querySelectorAll(".admin-sidebar-app-group").forEach(function (group) {
      var visible = !value || Boolean(group.querySelector('a:not([data-rmc-admin-search-hidden="1"])'));
      group.toggleAttribute("data-rmc-admin-search-hidden", !visible);
    });
    var status = sidebar.querySelector("#rmcTenantAdminNavSearchStatus");
    var empty = sidebar.querySelector("[data-rmc-admin-search-empty]");
    var reset = sidebar.querySelector("[data-rmc-admin-search-reset]");
    if (status) status.textContent = value ? (matches === 1 ? "1 matching destination" : matches + " matching destinations") : "";
    if (empty) empty.hidden = !value || matches > 0;
    if (reset) reset.hidden = !value;
  }

  function applyCompact(value) { document.body.classList.toggle("admin-sidebar-compact", value === true); }

  function updateConnection(sidebar) {
    var connectivity = sidebar.querySelector("[data-rmc-admin-connectivity]");
    var label = sidebar.querySelector("[data-rmc-admin-connectivity-label]");
    var offline = navigator.onLine === false;
    if (connectivity) {
      connectivity.dataset.offline = offline ? "1" : "0";
      connectivity.title = offline ? "Navigation changes will sync when the connection returns" : "Navigation preferences are synchronized";
    }
    if (label) label.textContent = offline ? "Offline ready" : "Synchronized";
    if (!offline && safeRead(pendingKey, null)) persist({});
  }

  function init() {
    var sidebar = document.getElementById("nav-sidebar");
    if (!sidebar || !sidebar.closest('[data-rmc-app-shell-host="tenant"]')) return;
    applyCompact(state.compact); renderPinned(sidebar); renderRecent(sidebar);

    var toggle = sidebar.querySelector("#admin-sidebar-compact-toggle");
    if (toggle) toggle.addEventListener("click", function () {
      state.compact = !document.body.classList.contains("admin-sidebar-compact");
      applyCompact(state.compact); persist({ compact: state.compact });
    });

    var pin = sidebar.querySelector("#admin-pin-this-page");
    if (pin) pin.addEventListener("click", function () {
      var path = window.location.pathname + window.location.search;
      if (state.pinned.some(function (row) { return row.path === path; })) { announce("This page is already pinned."); return; }
      if (state.pinned.length >= limits.pinned) { announce("Pinned is full. Unpin a page before adding another."); return; }
      var heading = document.querySelector("main h1, #content h1, h1");
      var label = text(heading && heading.textContent) || text(document.title) || path;
      state.pinned.push({ path: path, label: label.slice(0, 100) });
      renderPinned(sidebar); persist({ pinned: state.pinned }).then(function () { announce("Page pinned."); });
    });

    var pinnedList = sidebar.querySelector("#admin-sidebar-pinned-list");
    if (pinnedList) pinnedList.addEventListener("click", function (event) {
      var button = event.target.closest(".admin-unpin");
      if (!button || !button.dataset.path) return;
      state.pinned = state.pinned.filter(function (row) { return row.path !== button.dataset.path; });
      renderPinned(sidebar); persist({ pinned: state.pinned }).then(function () { announce("Page unpinned."); });
    });

    var clearRecent = sidebar.querySelector("[data-rmc-admin-recent-clear]");
    if (clearRecent) clearRecent.addEventListener("click", function () {
      state.recent = []; renderRecent(sidebar);
      persist({ recent: [] }).then(function () { announce("Recent pages cleared."); });
    });

    var input = sidebar.querySelector("#rmcTenantAdminNavSearch");
    var reset = sidebar.querySelector("[data-rmc-admin-search-reset]");
    if (input) {
      input.addEventListener("input", function () { filter(sidebar, input.value); });
      document.addEventListener("keydown", function (event) {
        if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !/input|textarea|select/i.test(event.target.tagName)) {
          event.preventDefault(); input.focus();
        }
      });
    }
    if (input && reset) reset.addEventListener("click", function () { input.value = ""; filter(sidebar, ""); input.focus(); });

    sidebar.addEventListener("keydown", function (event) {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      var nodes = focusables(sidebar), index = nodes.indexOf(event.target), next;
      if (!nodes.length) return;
      if (event.key === "ArrowDown") next = nodes[Math.min(nodes.length - 1, Math.max(0, index + 1))];
      else if (event.key === "ArrowUp") next = nodes[Math.max(0, index < 0 ? 0 : index - 1)];
      else if (event.key === "Home") next = nodes[0];
      else if (event.key === "End") next = nodes[nodes.length - 1];
      if (next) { event.preventDefault(); next.focus(); }
    });

    window.addEventListener("online", function () { updateConnection(sidebar); });
    window.addEventListener("offline", function () { updateConnection(sidebar); });
    updateConnection(sidebar); rememberCurrent(sidebar);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
