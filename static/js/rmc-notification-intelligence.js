/*
 * rmc-notification-intelligence.js — Surface 6: live notification center.
 *
 * The platform already has the pieces: a bell-badge poller
 * (rmc-notification-bell-poll.js), a toast system that self-persists into the
 * inbox (components__toast_notifications-1.js), the Notification REST API, and a
 * full SSR inbox page. What was missing is the connective tissue:
 *
 *   1. The avatar shows only an unread COUNT — the "Notifications (3)" item in
 *      the account menu is a dead link to a full page. You cannot see WHAT the 3
 *      are, nor clear one, without a navigation.
 *   2. The toast's own bell-bump only touches the operator topbar bell
 *      (.cp-topbar-bell / [data-rmc-header-bell]); it never moves the tenant
 *      avatar's [data-rmc-unread-badge], so a self-captured toast doesn't reflect
 *      on the tenant bell until the next 60s poll.
 *
 * This engine COMPOSES (never duplicates) those systems:
 *   - bellPreview   — lazily fetches the unread list and renders a live in-place
 *                     mini-inbox under the account-menu Notifications row.
 *   - inlineActions — per-item "mark read" + "mark all read", optimistic, with
 *                     instant badge sync (decrements all [data-rmc-unread-badge]).
 *   - toastSync     — wraps window.showToast so a self-captured toast bumps the
 *                     tenant badge the instant it fires (closes gap #2).
 *
 * All config comes from the #rmc-notification-config island (URLs reversed
 * server-side, capability flags from the SITE cascade). CSP-safe: every node is
 * built with createElement + textContent — never innerHTML of server data.
 * Fully self-guarded so a hiccup can never break the page chrome; no-ops when
 * its hooks are absent (e.g. shells without the avatar bell).
 */
(function () {
  "use strict";

  if (window.__rmcNotificationIntelligenceInit) {
    return;
  }
  window.__rmcNotificationIntelligenceInit = true;

  function readConfig() {
    var el = document.getElementById("rmc-notification-config");
    if (!el) {
      return null;
    }
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (e) {
      return null;
    }
  }

  var cfg = readConfig();
  if (!cfg || cfg.intelligence === false) {
    return;
  }

  var CACHE_MS = 30000; // re-fetch the preview at most every 30s
  var MAX_PREVIEW = 6; // keep the menu compact; the SSR inbox shows the rest
  var MAX_DISPLAY = 99;
  var READ_SENTINEL = "987654321"; // matches {% url ... pk=987654321 %} in the island

  // ---- CSRF (mirrors the toast component's resolver) -----------------------
  function csrfToken() {
    var m = (document.cookie || "").match(/csrftoken=([^;]+)/);
    if (m) {
      return m[1];
    }
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) {
      return meta.content;
    }
    var inp = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return inp ? inp.value : "";
  }

  // ---- Badge sync (replicates the poller's avatar/pill rules so the two -----
  // ---- never disagree; the 60s poll reconciles after any drift) ------------
  function currentUnread() {
    var badge = document.querySelector(
      '[data-rmc-unread-badge][data-rmc-unread-badge-style="pill"]'
    );
    if (!badge) {
      badge = document.querySelector("[data-rmc-unread-badge]");
    }
    if (!badge) {
      return 0;
    }
    var n = parseInt((badge.textContent || "").replace(/[^0-9]/g, ""), 10);
    return isNaN(n) || n < 0 ? 0 : n;
  }

  function applyUnread(count) {
    if (count < 0) {
      count = 0;
    }
    var text = count > MAX_DISPLAY ? MAX_DISPLAY + "+" : String(count);
    var badges = document.querySelectorAll("[data-rmc-unread-badge]");
    for (var i = 0; i < badges.length; i++) {
      var badge = badges[i];
      var style = badge.getAttribute("data-rmc-unread-badge-style") || "avatar";
      if (style === "avatar") {
        if (count > 0) {
          badge.textContent = text;
          badge.removeAttribute("hidden");
        } else {
          badge.textContent = "";
          badge.setAttribute("hidden", "hidden");
        }
      } else {
        badge.textContent = text;
      }
    }
  }

  function adjustUnread(delta) {
    applyUnread(currentUnread() + delta);
  }

  // ---- Severity grammar (mirrors the toast + SSR inbox contract) -----------
  function severityMeta(sev) {
    switch ((sev || "").toUpperCase()) {
      case "ALERT":
        return { cls: "rmc-noti-ic--alert", icon: "bi-exclamation-octagon-fill" };
      case "WARNING":
        return { cls: "rmc-noti-ic--warn", icon: "bi-exclamation-triangle-fill" };
      default:
        return { cls: "rmc-noti-ic--info", icon: "bi-info-circle-fill" };
    }
  }

  function timeAgo(iso) {
    try {
      var then = new Date(iso).getTime();
      if (isNaN(then)) {
        return "";
      }
      var secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
      if (secs < 60) {
        return "just now";
      }
      var mins = Math.floor(secs / 60);
      if (mins < 60) {
        return mins + "m ago";
      }
      var hrs = Math.floor(mins / 60);
      if (hrs < 24) {
        return hrs + "h ago";
      }
      var days = Math.floor(hrs / 24);
      if (days < 7) {
        return days + "d ago";
      }
      return Math.floor(days / 7) + "w ago";
    } catch (e) {
      return "";
    }
  }

  // ---- Network -------------------------------------------------------------
  function fetchUnread() {
    if (!cfg.listUrl) {
      return Promise.resolve(null);
    }
    var sep = cfg.listUrl.indexOf("?") === -1 ? "?" : "&";
    var url = cfg.listUrl + sep + "is_read=false&days=7";
    return fetch(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
    })
      .then(function (resp) {
        return resp.ok ? resp.json() : null;
      })
      .catch(function () {
        return null;
      });
  }

  function postMarkRead(id) {
    if (!cfg.readUrlTemplate) {
      return Promise.resolve(false);
    }
    var url = cfg.readUrlTemplate.replace(READ_SENTINEL, String(id));
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (resp) {
        return resp.ok;
      })
      .catch(function () {
        return false;
      });
  }

  function postMarkAll() {
    if (!cfg.markAllUrl) {
      return Promise.resolve(false);
    }
    return fetch(cfg.markAllUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (resp) {
        return resp.ok;
      })
      .catch(function () {
        return false;
      });
  }

  // ---- Preview rendering (CSP-safe; createElement + textContent only) ------
  var state = { panel: null, listBox: null, fetchedAt: 0, loading: false };

  function buildItem(n) {
    var meta = severityMeta(n.severity);
    var row = document.createElement("div");
    row.className = "rmc-noti-item";
    row.setAttribute("data-rmc-noti-id", String(n.id));

    var ic = document.createElement("span");
    ic.className = "rmc-noti-item__ic " + meta.cls;
    var i = document.createElement("i");
    i.className = "bi " + meta.icon;
    i.setAttribute("aria-hidden", "true");
    ic.appendChild(i);

    var bd = document.createElement(n.link ? "a" : "div");
    bd.className = "rmc-noti-item__bd";
    if (n.link) {
      bd.setAttribute("href", n.link);
    }
    var t = document.createElement("div");
    t.className = "rmc-noti-item__t";
    t.textContent = n.title || "Notification";
    var m = document.createElement("div");
    m.className = "rmc-noti-item__m";
    m.textContent = n.message || "";
    var tm = document.createElement("div");
    tm.className = "rmc-noti-item__time";
    tm.textContent = timeAgo(n.created_at);
    bd.appendChild(t);
    bd.appendChild(m);
    bd.appendChild(tm);

    row.appendChild(ic);
    row.appendChild(bd);

    if (cfg.inlineActions !== false) {
      var rd = document.createElement("button");
      rd.type = "button";
      rd.className = "rmc-noti-item__rd";
      rd.textContent = "Mark read";
      rd.setAttribute("aria-label", "Mark “" + (n.title || "notification") + "” as read");
      rd.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        rd.disabled = true;
        adjustUnread(-1); // optimistic
        row.parentNode && row.parentNode.removeChild(row);
        ensureEmptyState();
        postMarkRead(n.id).then(function (ok) {
          if (!ok) {
            state.fetchedAt = 0; // force refetch next open to self-correct
          }
        });
      });
      row.appendChild(rd);
    }
    return row;
  }

  function ensureEmptyState() {
    if (!state.listBox) {
      return;
    }
    if (state.listBox.querySelector(".rmc-noti-item")) {
      return;
    }
    if (state.listBox.querySelector(".rmc-noti-empty")) {
      return;
    }
    var empty = document.createElement("div");
    empty.className = "rmc-noti-empty";
    empty.textContent = "You’re all caught up";
    state.listBox.appendChild(empty);
  }

  function renderList(items) {
    if (!state.listBox) {
      return;
    }
    state.listBox.textContent = "";
    if (!items || !items.length) {
      ensureEmptyState();
      return;
    }
    var slice = items.slice(0, MAX_PREVIEW);
    for (var i = 0; i < slice.length; i++) {
      state.listBox.appendChild(buildItem(slice[i]));
    }
  }

  function buildPanel(anchorLi) {
    var li = document.createElement("li");
    li.className = "rmc-noti-preview";
    li.setAttribute("role", "group");
    li.setAttribute("aria-label", "Recent notifications");

    var hd = document.createElement("div");
    hd.className = "rmc-noti-preview__hd";
    var label = document.createElement("span");
    label.className = "rmc-noti-preview__title";
    label.textContent = "Recent";
    hd.appendChild(label);

    if (cfg.inlineActions !== false) {
      var allBtn = document.createElement("button");
      allBtn.type = "button";
      allBtn.className = "rmc-noti-preview__all";
      allBtn.textContent = "Mark all read";
      allBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        allBtn.disabled = true;
        applyUnread(0); // optimistic
        renderList([]);
        postMarkAll().then(function (ok) {
          allBtn.disabled = false;
          if (!ok) {
            state.fetchedAt = 0;
          }
        });
      });
      hd.appendChild(allBtn);
    }

    var listBox = document.createElement("div");
    listBox.className = "rmc-noti-preview__list";

    li.appendChild(hd);
    li.appendChild(listBox);
    state.panel = li;
    state.listBox = listBox;

    // Insert directly under the account-menu Notifications row.
    if (anchorLi && anchorLi.parentNode) {
      if (anchorLi.nextSibling) {
        anchorLi.parentNode.insertBefore(li, anchorLi.nextSibling);
      } else {
        anchorLi.parentNode.appendChild(li);
      }
    }
    return li;
  }

  function loadingState() {
    if (!state.listBox) {
      return;
    }
    state.listBox.textContent = "";
    var l = document.createElement("div");
    l.className = "rmc-noti-loading";
    l.textContent = "Loading…";
    state.listBox.appendChild(l);
  }

  function refresh(force) {
    if (state.loading) {
      return;
    }
    if (!force && Date.now() - state.fetchedAt < CACHE_MS) {
      return; // fresh enough
    }
    state.loading = true;
    if (!state.listBox.querySelector(".rmc-noti-item")) {
      loadingState();
    }
    fetchUnread().then(function (data) {
      state.loading = false;
      state.fetchedAt = Date.now();
      if (!data) {
        // keep whatever is there; show empty only if nothing rendered
        ensureEmptyState();
        return;
      }
      var items = data.results || data.notifications || [];
      renderList(items);
    });
  }

  // ---- Wiring: the account-dropdown bell preview ---------------------------
  function findAnchorLi() {
    var pill = document.querySelector(
      '[data-rmc-unread-badge][data-rmc-unread-badge-style="pill"]'
    );
    if (pill && pill.closest) {
      var li = pill.closest("li");
      if (li) {
        return li;
      }
    }
    return null;
  }

  function onOpen() {
    if (cfg.bellPreview === false) {
      return;
    }
    if (!state.panel) {
      var anchor = findAnchorLi();
      if (!anchor) {
        return;
      }
      buildPanel(anchor);
    }
    refresh(false);
  }

  function wirePreview() {
    var wrapper = document.querySelector("[data-rmc-unread-endpoint]");
    if (!wrapper) {
      return;
    }
    // Primary signal: the dropdown trigger click (framework-agnostic — does not
    // depend on Bootstrap's JS being loaded yet). The menu opens on the same
    // click; defer one tick so the panel mounts into an open menu.
    var trigger =
      wrapper.querySelector('[data-bs-toggle="dropdown"]') ||
      wrapper.querySelector(".user-dropdown-trigger");
    if (trigger) {
      trigger.addEventListener("click", function () {
        window.setTimeout(onOpen, 0);
      });
    }
    // Belt-and-suspenders: honour Bootstrap's own event if it fires.
    document.addEventListener("show.bs.dropdown", function (ev) {
      if (ev.target && wrapper.contains(ev.target)) {
        window.setTimeout(onOpen, 0);
      }
    });
  }

  // ---- Wiring: instant tenant-badge sync on toast self-capture -------------
  function wireToastSync() {
    if (cfg.toastSync === false) {
      return;
    }
    var wrapped = false;
    function wrap() {
      if (wrapped || typeof window.showToast !== "function") {
        return wrapped;
      }
      var original = window.showToast;
      window.showToast = function (message, type, third) {
        try {
          original.apply(this, arguments);
        } finally {
          try {
            // A self-captured toast adds exactly one unread row. The operator
            // topbar bell is already bumped by the toast module; this closes the
            // gap for the tenant avatar [data-rmc-unread-badge].
            adjustUnread(1);
            state.fetchedAt = 0; // next open refetches so the preview shows it
          } catch (e) {
            /* never break a toast on a badge hiccup */
          }
        }
      };
      wrapped = true;
      return true;
    }
    if (!wrap()) {
      // showToast may be defined after us (load-order independent) — retry once.
      window.setTimeout(wrap, 1200);
    }
  }

  function init() {
    try {
      wirePreview();
    } catch (e) {
      /* chrome must survive */
    }
    try {
      wireToastSync();
    } catch (e) {
      /* chrome must survive */
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
