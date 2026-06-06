/**
 * RunMyCampus assist dock — unified bottom-right rail (AI, feedback, help, messages, top).
 */
(function () {
  "use strict";

  var PANEL_ATTR = "data-rmc-assist-panel";

  function labels() {
    var el = document.getElementById("page-data-rmc-assist-dock");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (_e) {
      return {};
    }
  }

  function dockUrls() {
    var L = labels();
    return (L && L.urls) || {};
  }

  function dockUrl(key, fallback) {
    var u = dockUrls()[key];
    if (u && String(u).length) return String(u);
    // Fallback only when the labels island is absent (legacy pages); production
    // shells always ship rmc_assist_dock_labels.html with ASSIST_DOCK_URLS_JSON.
    if (!document.getElementById("page-data-rmc-assist-dock")) {
      return fallback || "";
    }
    return "";
  }

  // v4.00.91 — registry SOT island. Optional; falls back to legacy DOM-scan
  // when missing so older shells keep working during the migration window.
  function registry() {
    var el = document.getElementById("page-data-rmc-assist-dock-registry");
    if (!el) return null;
    try {
      var parsed = JSON.parse(el.textContent || "null");
      if (!parsed || !Array.isArray(parsed.slots)) return null;
      return parsed;
    } catch (_e) {
      return null;
    }
  }

  // Look up a slot in the registry by its canonical id.
  function findSlot(reg, slotId) {
    if (!reg || !Array.isArray(reg.slots)) return null;
    for (var i = 0; i < reg.slots.length; i++) {
      if (reg.slots[i].id === slotId) return reg.slots[i];
    }
    return null;
  }

  // Resolve the DOM source for a slot. Returns the element or null.
  // Skips body / html so a stray data-rmc-page-help on <body> doesn't
  // get adopted as the help chip.
  function resolveAdoptedNode(slot) {
    if (!slot || slot.source !== "dom-adopt" || !slot.adopt_selector) return null;
    var nodes = document.querySelectorAll(slot.adopt_selector);
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (node === document.body || node === document.documentElement) continue;
      if (node.closest && node.closest("[data-rmc-copilot-rail]")) continue;
      return node;
    }
    return null;
  }

  function backdropEl() {
    return document.querySelector(".rmc-assist-dock__backdrop");
  }

  function dockEl() {
    return document.querySelector(".rmc-assist-dock");
  }

  function syncBackdrop() {
    var bd = backdropEl();
    if (!bd) return;
    var open =
      document.body.getAttribute(PANEL_ATTR) === "ai" ||
      document.body.getAttribute(PANEL_ATTR) === "feedback";
    bd.hidden = !open;
    var dock = dockEl();
    if (dock) dock.classList.toggle("rmc-assist-dock--panel-open", open);
  }

  function closeAll(except) {
    if (except !== "ai") {
      var panel = document.getElementById("aiCopilotPanel");
      var trigger = document.getElementById("aiCopilotTrigger");
      if (panel) panel.classList.remove("active");
      if (trigger) trigger.setAttribute("aria-expanded", "false");
    }
    if (except !== "feedback") {
      var fb = document.querySelector(".rmc-assist-panel--feedback");
      var fbBtn = document.querySelector("[data-rmc-assist-feedback-toggle]");
      if (fb) {
        fb.classList.remove("rmc-assist-panel--open");
        fb.dataset.open = "false";
      }
      if (fbBtn) fbBtn.setAttribute("aria-expanded", "false");
    }
    if (!except) document.body.removeAttribute(PANEL_ATTR);
    syncBackdrop();
  }

  // v4.00.91 — annotate every adopted chip with its registry slot id so
  // downstream layers (badges in Wave B, presence in Wave C, AI deep
  // features in Wave D) can target chips by slot id rather than by
  // their original CSS class. Idempotent — safe to re-run.
  function annotateAdoptedSlots() {
    var reg = registry();
    if (!reg) return 0;
    var marked = 0;
    for (var i = 0; i < reg.slots.length; i++) {
      var slot = reg.slots[i];
      if (slot.source !== "dom-adopt") continue;
      var node = resolveAdoptedNode(slot);
      if (!node) continue;
      // Mark the source node AND, if the dock has already mounted, the
      // adopted button (which is the same DOM node, just re-parented).
      if (!node.hasAttribute("data-rmc-assist-slot-id")) {
        node.setAttribute("data-rmc-assist-slot-id", slot.id);
        marked++;
      }
      if (slot.shortcut && !node.getAttribute("data-rmc-assist-shortcut")) {
        node.setAttribute("data-rmc-assist-shortcut", slot.shortcut);
      }
      if (slot.aria_keyshortcuts && !node.getAttribute("aria-keyshortcuts")) {
        node.setAttribute("aria-keyshortcuts", slot.aria_keyshortcuts);
      }
    }
    return marked;
  }

  /** Measured height of the dock rail — drives back-to-top lift + notebook offset. */
  function syncAssistRailMetrics(dock) {
    if (!dock) dock = document.querySelector(".rmc-assist-dock");
    var rail = dock && dock.querySelector(".rmc-assist-dock__rail");
    if (!rail) return;
    var h = Math.ceil(rail.getBoundingClientRect().height);
    if (!h) return;
    document.documentElement.style.setProperty("--rmc-assist-rail-height", h + "px");
  }

  function watchAssistRailMetrics(dock) {
    if (!dock) return;
    var rail = dock.querySelector(".rmc-assist-dock__rail");
    if (!rail) return;
    syncAssistRailMetrics(dock);
    if (typeof ResizeObserver === "undefined") return;
    if (dock.__rmcRailMetricsObs) {
      dock.__rmcRailMetricsObs.disconnect();
    }
    var ro = new ResizeObserver(function () {
      syncAssistRailMetrics(dock);
    });
    ro.observe(rail);
    dock.__rmcRailMetricsObs = ro;
  }

  window.RMCAssistDock = {
    closeAll: closeAll,
    syncBackdrop: syncBackdrop,
    syncAssistRailMetrics: syncAssistRailMetrics,
    // Wave A introspection helpers — Wave B will append badge / presence
    // wiring under the same namespace.
    registrySnapshot: function () { return registry(); },
    findSlot: function (id) { return findSlot(registry(), id); },
    annotateAdoptedSlots: annotateAdoptedSlots,
  };

  function shouldForceOperatorToolsMount() {
    return !!document.getElementById("page-data-rmc-operator-tools");
  }

  function mountDock(L) {
    var aiWrap = document.querySelector(".ai-copilot-wrapper");
    var contextToggle = document.querySelector(".cp-context-drawer-toggle");
    var voc = document.querySelector(".voc-widget");
    var helpBtn = null;
    var helpCandidates = document.querySelectorAll("[data-rmc-page-help]");
    for (var hi = 0; hi < helpCandidates.length; hi++) {
      var candidate = helpCandidates[hi];
      if (candidate === document.body || candidate === document.documentElement) {
        continue;
      }
      if (candidate.closest && candidate.closest("[data-rmc-copilot-rail]")) {
        continue;
      }
      helpBtn = candidate;
      break;
    }
    var backBtn = document.getElementById("back-to-top-btn");
    var chat = document.querySelector(".portal-chathead");
    if (
      !aiWrap &&
      !voc &&
      !helpBtn &&
      !backBtn &&
      !chat &&
      !contextToggle &&
      !shouldForceOperatorToolsMount()
    ) {
      return;
    }

    var dock = document.createElement("div");
    dock.className = "rmc-assist-dock";
    dock.setAttribute("data-rmc-assist-dock", "1");
    dock.innerHTML =
      '<div class="rmc-assist-dock__backdrop" hidden></div>' +
      '<div class="rmc-assist-dock__panels"></div>' +
      '<nav class="rmc-assist-dock__rail" aria-label="' +
      (L.toolbar || "Page assistants") +
      '">' +
      '<div id="rmc-assist-secondary-actions" class="rmc-assist-dock__secondary" hidden></div>' +
      '<div class="rmc-assist-dock__primary-row"></div>' +
      "</nav>";

    var panels = dock.querySelector(".rmc-assist-dock__panels");
    var secondary = dock.querySelector(".rmc-assist-dock__secondary");
    var primaryRow = dock.querySelector(".rmc-assist-dock__primary-row");
    var backdrop = dock.querySelector(".rmc-assist-dock__backdrop");

    var expandBtn = document.createElement("button");
    expandBtn.type = "button";
    expandBtn.className = "rmc-assist-dock__btn rmc-assist-dock__btn--expand";
    expandBtn.setAttribute("data-rmc-assist-expand", "");
    expandBtn.setAttribute("aria-expanded", "false");
    expandBtn.setAttribute("aria-controls", "rmc-assist-secondary-actions");
    expandBtn.title = L.expand || "More assistants";
    expandBtn.innerHTML =
      '<i class="bi bi-plus-lg" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
      (L.expand || "More") +
      "</span>";
    primaryRow.appendChild(expandBtn);

    function slot(node, className) {
      var wrap = document.createElement("div");
      wrap.className = "rmc-assist-dock__slot " + (className || "");
      wrap.appendChild(node);
      secondary.appendChild(wrap);
    }

    if (backBtn) {
      backBtn.classList.add("rmc-back-to-top--floating");
      backBtn.setAttribute("aria-label", L.backToTop || "Back to top");
      document.body.setAttribute("data-rmc-back-to-top-floating", "1");
    }

    if (chat) {
      chat.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--messages");
      slot(chat, "rmc-assist-dock__slot--messages");
    }

    if (voc) {
      var vocPanel = voc.querySelector(".voc-widget__panel");
      var vocToggle = voc.querySelector("[data-voc-toggle]");
      if (vocPanel && vocToggle) {
        vocPanel.classList.add("rmc-assist-panel", "rmc-assist-panel--feedback");
        vocPanel.id = vocPanel.id || "rmc-assist-feedback-panel";
        vocPanel.dataset.open = "false";
        panels.appendChild(vocPanel);
        vocToggle.classList.add(
          "rmc-assist-dock__btn",
          "rmc-assist-dock__btn--feedback"
        );
        vocToggle.setAttribute("data-rmc-assist-feedback-toggle", "");
        vocToggle.setAttribute("aria-controls", vocPanel.id);
        vocToggle.setAttribute("aria-expanded", "false");
        vocToggle.setAttribute("aria-haspopup", "dialog");
        vocToggle.innerHTML =
          '<i class="bi bi-chat-heart" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
          (L.feedback || "Feedback") +
          "</span>";
        slot(vocToggle, "rmc-assist-dock__slot--feedback");
      }
      voc.remove();
    }

    if (contextToggle) {
      contextToggle.classList.add(
        "rmc-assist-dock__btn",
        "rmc-assist-dock__btn--context"
      );
      contextToggle.classList.remove(
        "position-fixed",
        "bottom-0",
        "end-0",
        "m-3"
      );
      if (!contextToggle.querySelector(".rmc-assist-dock__label")) {
        var ctxLbl = document.createElement("span");
        ctxLbl.className = "rmc-assist-dock__label";
        ctxLbl.textContent = L.context || "Context";
        contextToggle.appendChild(ctxLbl);
      }
      slot(contextToggle, "rmc-assist-dock__slot--context");
    }

    if (helpBtn) {
      helpBtn.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--help");
      if (!helpBtn.querySelector("i.bi")) {
        helpBtn.innerHTML =
          '<i class="bi bi-question-circle" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
          (L.help || "Help") +
          "</span>";
      } else if (!helpBtn.querySelector(".rmc-assist-dock__label")) {
        var span = document.createElement("span");
        span.className = "rmc-assist-dock__label";
        span.textContent = L.help || "Help";
        helpBtn.appendChild(span);
      }
      slot(helpBtn, "rmc-assist-dock__slot--help");
    }

    if (aiWrap) {
      var aiPanel = aiWrap.querySelector("#aiCopilotPanel");
      var aiTrigger = aiWrap.querySelector("#aiCopilotTrigger");
      var hint = aiWrap.querySelector(".ai-shortcut-hint");
      if (aiPanel && aiTrigger) {
        aiPanel.classList.add("rmc-assist-panel", "rmc-assist-panel--ai");
        panels.appendChild(aiPanel);
        aiTrigger.classList.add("rmc-assist-dock__btn", "rmc-assist-dock__btn--ai");
        if (!aiTrigger.querySelector(".rmc-assist-dock__label")) {
          var aiLbl = document.createElement("span");
          aiLbl.className = "rmc-assist-dock__label";
          aiLbl.textContent = L.ai || "AI Copilot";
          aiTrigger.appendChild(aiLbl);
        }
        primaryRow.appendChild(aiTrigger);
        if (hint) dock.appendChild(hint);
      }
      aiWrap.remove();
    }

    document.body.appendChild(dock);
    document.body.setAttribute("data-rmc-assist-dock", "mounted");

    expandBtn.addEventListener("click", function () {
      var show = secondary.hidden;
      secondary.hidden = !show;
      expandBtn.setAttribute("aria-expanded", show ? "true" : "false");
      expandBtn.querySelector("i").className = show
        ? "bi bi-x-lg"
        : "bi bi-plus-lg";
      expandBtn.title = show ? L.collapse || "Fewer" : L.expand || "More";
      dock.classList.toggle("rmc-assist-dock--expanded", show);
      window.requestAnimationFrame(function () {
        syncAssistRailMetrics(dock);
      });
    });

    backdrop.addEventListener("click", function () {
      closeAll();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key !== "Escape") return;
      if (document.body.getAttribute(PANEL_ATTR)) {
        closeAll();
        return;
      }
      if (expandBtn.getAttribute("aria-expanded") === "true") {
        secondary.hidden = true;
        expandBtn.setAttribute("aria-expanded", "false");
        expandBtn.querySelector("i").className = "bi bi-plus-lg";
        dock.classList.remove("rmc-assist-dock--expanded");
      }
    });

    document.addEventListener("click", function (e) {
      if (e.target.closest(".rmc-assist-dock__rail")) return;
      var fbPanel = document.querySelector(".rmc-assist-panel--feedback");
      var fbBtn = e.target.closest("[data-rmc-assist-feedback-toggle]");
      if (
        fbPanel &&
        fbPanel.classList.contains("rmc-assist-panel--open") &&
        !fbPanel.contains(e.target) &&
        !fbBtn
      ) {
        closeAll();
      }
      var aiPanel = document.getElementById("aiCopilotPanel");
      if (
        aiPanel &&
        aiPanel.classList.contains("active") &&
        !aiPanel.contains(e.target) &&
        !e.target.closest("#aiCopilotTrigger")
      ) {
        closeAll();
      }
    });

    var visibleSecondary = Array.prototype.filter.call(
      secondary.querySelectorAll(".rmc-assist-dock__slot"),
      function (slot) {
        return slot.offsetParent !== null;
      }
    );
    if (!visibleSecondary.length) {
      expandBtn.hidden = true;
      secondary.hidden = true;
    }

    watchAssistRailMetrics(dock);

    if (window.__rmcVocReinit) window.__rmcVocReinit();
    document.dispatchEvent(new CustomEvent("rmc-assist-dock-mounted"));
    if (window.RMCBackToTop && window.RMCBackToTop.refresh) {
      window.RMCBackToTop.refresh();
    }
  }

  // Wave B — context polling, badge painting, predictive halo + click tracking.
  // -----------------------------------------------------------------------

  var CONTEXT_URL = dockUrl("context", "/assist-dock/context.json");
  var POLL_INTERVAL_MS = 60000; // 60s default; respects visibility state
  var OUTAGE_BACKOFF_MS = 30000;

  function isPlatformOutageStatus(status) {
    return !status || (status >= 502 && status <= 504);
  }
  var HALO_HISTORY_KEY = "rmc_dock_clicks_v1";
  var HALO_HISTORY_TTL_DAYS = 30;
  var HALO_MIN_CLICKS_TO_PROMOTE = 3;
  var HALO_COOLDOWN_MS = 5 * 60 * 1000; // don't re-halo a slot for 5 min after click

  function getChipForSlot(slotId) {
    if (!slotId) return null;
    var sel = '[data-rmc-assist-slot-id="' + slotId.replace(/"/g, '\\"') + '"]';
    return document.querySelector(sel);
  }

  function paintBadge(chip, snapshot) {
    if (!chip) return;
    var existing = chip.querySelector(".rmc-assist-dock__badge");
    if (!snapshot) {
      if (existing) existing.remove();
      chip.removeAttribute("data-rmc-badge-count");
      chip.removeAttribute("data-rmc-badge-level");
      return;
    }
    var level = snapshot.level || "info";
    var count = snapshot.count;
    var dot = !!snapshot.dot;
    var pill = existing;
    if (!pill) {
      pill = document.createElement("span");
      pill.className = "rmc-assist-dock__badge";
      pill.setAttribute("aria-hidden", "true");
      chip.appendChild(pill);
    }
    pill.dataset.rmcBadgeLevel = level;
    if (count != null) {
      pill.textContent = count > 99 ? "99+" : String(count);
      pill.classList.remove("rmc-assist-dock__badge--dot-only");
    } else if (dot) {
      pill.textContent = "";
      pill.classList.add("rmc-assist-dock__badge--dot-only");
    } else {
      pill.remove();
      chip.removeAttribute("data-rmc-badge-count");
      chip.removeAttribute("data-rmc-badge-level");
      return;
    }
    chip.setAttribute("data-rmc-badge-level", level);
    if (count != null) chip.setAttribute("data-rmc-badge-count", String(count));
    if (snapshot.tooltip) chip.setAttribute("title", snapshot.tooltip);
  }

  function applyBadges(badges) {
    if (!badges || typeof badges !== "object") return;
    // Clear stale badges first — any chip with a badge that's no longer
    // in the payload should drop its pill.
    var chipsWithBadges = document.querySelectorAll("[data-rmc-assist-slot-id][data-rmc-badge-level]");
    for (var i = 0; i < chipsWithBadges.length; i++) {
      var slotId = chipsWithBadges[i].getAttribute("data-rmc-assist-slot-id");
      if (!Object.prototype.hasOwnProperty.call(badges, slotId)) {
        paintBadge(chipsWithBadges[i], null);
      }
    }
    Object.keys(badges).forEach(function (slotId) {
      var chip = getChipForSlot(slotId);
      if (chip) paintBadge(chip, badges[slotId]);
    });
  }

  // ---- Predictive halo (client-only frequency model, no server roundtrip) ----

  function readHaloHistory() {
    try {
      var raw = localStorage.getItem(HALO_HISTORY_KEY);
      if (!raw) return {};
      var parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : {};
    } catch (_e) {
      return {};
    }
  }

  function writeHaloHistory(obj) {
    try {
      localStorage.setItem(HALO_HISTORY_KEY, JSON.stringify(obj));
    } catch (_e) {
      /* quota or disabled — silent */
    }
  }

  function pageKey() {
    try {
      // Use pathname only — query string would shard history pointlessly.
      return location.pathname || "/";
    } catch (_e) {
      return "/";
    }
  }

  function recordChipClick(slotId) {
    if (!slotId) return;
    var key = pageKey();
    var hist = readHaloHistory();
    if (!hist[key]) hist[key] = { slots: {}, lastClickAt: {} };
    var bucket = hist[key];
    bucket.slots[slotId] = (bucket.slots[slotId] || 0) + 1;
    bucket.lastClickAt[slotId] = Date.now();
    writeHaloHistory(prunedHistory(hist));
  }

  function prunedHistory(hist) {
    var cutoff = Date.now() - HALO_HISTORY_TTL_DAYS * 24 * 60 * 60 * 1000;
    Object.keys(hist).forEach(function (key) {
      var bucket = hist[key];
      var anyRecent = false;
      Object.keys(bucket.lastClickAt || {}).forEach(function (slotId) {
        if ((bucket.lastClickAt[slotId] || 0) >= cutoff) anyRecent = true;
      });
      if (!anyRecent) delete hist[key];
    });
    return hist;
  }

  function pickHaloSlot() {
    var hist = readHaloHistory();
    var bucket = hist[pageKey()];
    if (!bucket || !bucket.slots) return null;
    var now = Date.now();
    var best = null;
    var bestCount = HALO_MIN_CLICKS_TO_PROMOTE - 1;
    Object.keys(bucket.slots).forEach(function (slotId) {
      var count = bucket.slots[slotId] || 0;
      if (count <= bestCount) return;
      var lastAt = (bucket.lastClickAt || {})[slotId] || 0;
      if (now - lastAt < HALO_COOLDOWN_MS) return;
      best = slotId;
      bestCount = count;
    });
    return best;
  }

  function applyHalo() {
    var prior = document.querySelectorAll(".rmc-assist-dock__btn--halo");
    for (var i = 0; i < prior.length; i++) {
      prior[i].classList.remove("rmc-assist-dock__btn--halo");
      prior[i].removeAttribute("data-rmc-halo-promoted");
    }
    var target = pickHaloSlot();
    if (!target) return;
    var chip = getChipForSlot(target);
    if (!chip) return;
    chip.classList.add("rmc-assist-dock__btn--halo");
    chip.setAttribute("data-rmc-halo-promoted", "1");
  }

  function bindClickTracking() {
    document.addEventListener(
      "click",
      function (ev) {
        var node = ev.target;
        while (node && node !== document.body) {
          if (node.hasAttribute && node.hasAttribute("data-rmc-assist-slot-id")) {
            recordChipClick(node.getAttribute("data-rmc-assist-slot-id"));
            return;
          }
          node = node.parentNode;
        }
      },
      true
    );
  }

  function dispatchAssistDockContext(payload) {
    if (!payload || typeof payload !== "object") return;
    applyBadges(payload.badges || {});
    renderQuickActions(payload.quick_actions || []);
    applyHalo();
    window.dispatchEvent(
      new CustomEvent("rmc-assist-dock-context", { detail: payload })
    );
    if (payload.tools_tray && typeof payload.tools_tray === "object") {
      document.dispatchEvent(
        new CustomEvent("rmc-tools-tray-page-sync", {
          detail: { page: payload.tools_tray },
        })
      );
    }
  }

  function fetchContext() {
    if (_authRealtimeStopped || isAuthLanding()) return Promise.resolve();
    var url = CONTEXT_URL + "?page=" + encodeURIComponent(pageKey());
    try {
      return fetch(url, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          if (r.status === 401 || r.status === 403) {
            stopAuthRealtime();
            return null;
          }
          if (isPlatformOutageStatus(r.status)) return null;
          if (!r.ok) return null;
          var ct = (r.headers.get("content-type") || "").toLowerCase();
          if (ct && ct.indexOf("json") === -1) return null;
          return r.json();
        })
        .then(function (payload) {
          if (!payload) return;
          dispatchAssistDockContext(payload);
        })
        .catch(function () {
          /* network failure — silent, next poll will retry */
        });
    } catch (_e) {
      return Promise.resolve();
    }
  }

  function renderQuickActions(actions) {
    var dock = document.querySelector(".rmc-assist-dock");
    if (!dock) return;
    var holder = dock.querySelector("[data-rmc-assist-quick-actions]");
    if (!holder) {
      holder = document.createElement("div");
      holder.setAttribute("data-rmc-assist-quick-actions", "1");
      holder.className = "rmc-assist-dock__quick-actions";
      dock.insertBefore(holder, dock.querySelector(".rmc-assist-dock__rail"));
    }
    holder.innerHTML = "";
    if (!actions || !actions.length) {
      holder.hidden = true;
      return;
    }
    holder.hidden = false;
    for (var i = 0; i < actions.length; i++) {
      var a = actions[i];
      if (!a || !a.href) continue;
      var link = document.createElement("a");
      link.className = "rmc-assist-dock__quick-action";
      link.href = a.href;
      link.setAttribute("data-rmc-assist-quick-action-id", a.id || "");
      link.innerHTML =
        '<i class="bi ' +
        (a.icon || "bi-arrow-right-short").replace(/"/g, "") +
        '" aria-hidden="true"></i><span>' +
        (a.label || "").replace(/</g, "&lt;") +
        "</span>";
      holder.appendChild(link);
    }
  }

  function startPolling() {
    if (_authRealtimeStopped || isAuthLanding()) return;
    fetchContext();
    var timer = null;
    function schedule() {
      clearTimeout(timer);
      if (_authRealtimeStopped || document.hidden) return; // pause when tab is hidden
      timer = setTimeout(function () {
        fetchContext().then(schedule);
      }, POLL_INTERVAL_MS);
    }
    schedule();
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        fetchContext().then(schedule);
      } else {
        clearTimeout(timer);
      }
    });
  }

  // Wave C — render registry-source chips (source="registry" or "external").
  // The v1 dock only adopted DOM nodes; this pass paints brand-new chips
  // from the registry into the same primary/secondary row chrome.
  function mountRegistryChips() {
    var reg = registry();
    if (!reg || !Array.isArray(reg.slots)) return 0;
    var dock = document.querySelector(".rmc-assist-dock");
    if (!dock) return 0;
    var primary = dock.querySelector(".rmc-assist-dock__primary-row");
    var secondary = dock.querySelector(".rmc-assist-dock__secondary");
    if (!primary || !secondary) return 0;
    var rendered = 0;
    for (var i = 0; i < reg.slots.length; i++) {
      var slot = reg.slots[i];
      if (!slot || slot.source === "dom-adopt") continue;
      if (document.querySelector(
            '[data-rmc-assist-slot-id="' + (slot.id || "").replace(/"/g, '\\"') + '"]'
          )) {
        // Already rendered (e.g. by a re-init pass) — skip.
        continue;
      }
      var chip = buildRegistryChip(slot);
      if (!chip) continue;
      var slotWrap = document.createElement("div");
      slotWrap.className =
        "rmc-assist-dock__slot rmc-assist-dock__slot--" + (slot.id || "x");
      slotWrap.appendChild(chip);
      if (slot.pinned_default) {
        primary.appendChild(slotWrap);
      } else {
        secondary.appendChild(slotWrap);
      }
      rendered++;
    }
    if (rendered) {
      window.requestAnimationFrame(function () {
        syncAssistRailMetrics(dock);
      });
    }
    return rendered;
  }

  function buildRegistryChip(slot) {
    var el;
    if (slot.source === "external" && slot.href) {
      el = document.createElement("a");
      el.href = slot.href;
    } else {
      el = document.createElement("button");
      el.type = "button";
    }
    el.className =
      "rmc-assist-dock__btn rmc-assist-dock__btn--" + (slot.id || "x");
    el.setAttribute("data-rmc-assist-slot-id", slot.id || "");
    if (slot.shortcut) el.setAttribute("data-rmc-assist-shortcut", slot.shortcut);
    if (slot.aria_keyshortcuts) {
      el.setAttribute("aria-keyshortcuts", slot.aria_keyshortcuts);
    }
    if (slot.description) el.setAttribute("title", slot.description);
    el.innerHTML =
      '<i class="bi ' +
      (slot.icon || "bi-circle").replace(/"/g, "") +
      '" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
      (slot.label || "").replace(/</g, "&lt;") +
      "</span>";
    if (slot.source === "registry" && slot.id === "voice") {
      el.addEventListener("click", startVoiceCapture);
    }
    return el;
  }

  // Voice chip — Web Speech API → ⌘K dispatch. Requires user pref opt-in,
  // which the registry enforces via requires_feature="voice_assist". The
  // chip only renders when the feature flag flips on; the click handler
  // does the actual speech recognition.
  function startVoiceCapture() {
    var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      alert("Voice not supported in this browser.");
      return;
    }
    try {
      var rec = new SR();
      rec.lang = (document.documentElement.lang || "en") + "-US";
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.onresult = function (ev) {
        var phrase = ((ev.results[0] || [])[0] || {}).transcript || "";
        if (!phrase) return;
        // Dispatch into ⌘K if available.
        if (window.rmcCommandBar && window.rmcCommandBar.runQuery) {
          window.rmcCommandBar.runQuery(phrase);
        } else {
          window.dispatchEvent(
            new CustomEvent("rmc-assist-voice-phrase", { detail: { phrase: phrase } })
          );
        }
      };
      rec.start();
    } catch (_e) {
      /* abort — never crash the dock */
    }
  }

  // Wave D — AI action dispatcher. ``runAIAction(actionId, ctx)`` POSTs to
  // /assist-dock/ai/<action_id>/ with {page_path, page_excerpt, user_query}
  // and resolves with the response envelope. ``listInsights`` / ``clearInsight``
  // expose the proactive-insights ring to the AI panel.
  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content && meta.content !== "NOTPROVIDED") {
      return meta.content;
    }
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    m = document.cookie.match(/(?:^|; )rmc_manager_csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
    return "";
  }

  function runAIAction(actionId, ctx) {
    var payload = {
      page_path: (ctx && ctx.page_path) || location.pathname || "",
      page_excerpt: (ctx && ctx.page_excerpt) || "",
      user_query: (ctx && ctx.user_query) || "",
    };
    var tpl = dockUrl("ai_invoke", "/assist-dock/ai/{action_id}/");
    var url = tpl.replace("{action_id}", encodeURIComponent(actionId));
    try {
      return fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify(payload),
      }).then(function (r) {
        return r.json().then(function (envelope) {
          envelope.status = r.status;
          return envelope;
        });
      });
    } catch (_e) {
      return Promise.resolve({ ok: false, error: "network_failed", status: 0 });
    }
  }

  function listInsights(pagePath) {
    var url = dockUrl("insights", "/assist-dock/insights.json");
    if (pagePath) url += "?page=" + encodeURIComponent(pagePath);
    return fetch(url, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }).then(function (r) {
      if (!r.ok) return { insights: [] };
      return r.json();
    });
  }

  function clearInsight(insightId) {
    return fetch(dockUrl("insights_clear", "/assist-dock/insights/clear/"), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({ insight_id: insightId }),
    }).then(function (r) {
      return r.ok;
    });
  }

  // -----------------------------------------------------------------------
  // Wave E1 — presence heartbeat (every PRESENCE_HEARTBEAT_MS, paused when
  // tab is hidden).
  // -----------------------------------------------------------------------
  var PRESENCE_HEARTBEAT_MS = 30000;

  function sendPresenceHeartbeat() {
    var url = dockUrl("presence_heartbeat", "/assist-dock/presence/heartbeat/");
    try {
      return fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ page_path: pageKey() }),
      }).catch(function () {
        /* silent — best-effort */
      });
    } catch (_e) {
      return Promise.resolve();
    }
  }

  function startPresence() {
    sendPresenceHeartbeat();
    var timer = null;
    function schedule() {
      clearTimeout(timer);
      if (document.hidden) return;
      timer = setTimeout(function () {
        sendPresenceHeartbeat().then(schedule);
      }, PRESENCE_HEARTBEAT_MS);
    }
    schedule();
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        sendPresenceHeartbeat().then(schedule);
      } else {
        clearTimeout(timer);
      }
    });
  }

  // -----------------------------------------------------------------------
  // Wave E3 — SSE upgrade. EventSource subscribes to /context/stream/ and
  // applies badge frames as they arrive. Falls back to the existing 60s
  // poll when EventSource is missing OR when the stream errors twice in
  // a row.
  // -----------------------------------------------------------------------
  var _sseSource = null;
  var _sseErrorCount = 0;
  var _sseFallbackEngaged = false;
  var _authRealtimeStopped = false;

  function stopAuthRealtime() {
    _authRealtimeStopped = true;
    _sseFallbackEngaged = true;
    if (_sseSource) {
      try { _sseSource.close(); } catch (_e) {}
      _sseSource = null;
    }
    if (_cursorPollTimer) {
      clearInterval(_cursorPollTimer);
      _cursorPollTimer = null;
    }
  }

  function startSSE() {
    if (_authRealtimeStopped || isAuthLanding()) return false;
    if (_sseFallbackEngaged) return false;
    if (typeof EventSource === "undefined") return false;
    if (_sseSource !== null) return true;
    try {
      var base = dockUrl("context_stream", "/assist-dock/context/stream/");
      var url = base + (base.indexOf("?") >= 0 ? "&" : "?") + "page=" + encodeURIComponent(pageKey());
      _sseSource = new EventSource(url, { withCredentials: true });
    } catch (_e) {
      _sseFallbackEngaged = true;
      return false;
    }
    _sseSource.addEventListener("snapshot", function (ev) {
      try {
        var payload = JSON.parse(ev.data);
        dispatchAssistDockContext(payload);
      } catch (_e) {
        /* malformed frame — ignore */
      }
    });
    _sseSource.addEventListener("badges", function (ev) {
      try {
        var payload = JSON.parse(ev.data);
        applyBadges(payload.badges || {});
      } catch (_e) {
        /* ignore */
      }
    });
    _sseSource.addEventListener("heartbeat", function () {
      /* no-op — proxy keep-alive */
    });
    _sseSource.addEventListener("done", function () {
      // Server closed cleanly; let EventSource auto-reconnect on its own
      // cadence. No fallback engagement.
    });
    _sseSource.onerror = function () {
      _sseErrorCount++;
      fetch(CONTEXT_URL + "?page=" + encodeURIComponent(pageKey()), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (r) {
          if (r.status === 401 || r.status === 403) {
            stopAuthRealtime();
            return;
          }
          if (isPlatformOutageStatus(r.status)) {
            try { _sseSource.close(); } catch (_e) {}
            _sseSource = null;
            window.setTimeout(function () {
              if (!_authRealtimeStopped) startSSE();
            }, OUTAGE_BACKOFF_MS);
            return;
          }
          if (_sseErrorCount >= 2) {
            try { _sseSource.close(); } catch (_e) {}
            _sseSource = null;
            _sseFallbackEngaged = true;
            startPolling();
          }
        })
        .catch(function () {
          try { _sseSource.close(); } catch (_e) {}
          _sseSource = null;
          window.setTimeout(function () {
            if (!_authRealtimeStopped) startSSE();
          }, OUTAGE_BACKOFF_MS);
        });
    };
    return true;
  }

  // -----------------------------------------------------------------------
  // Wave E5 — share short-link mint client + Wave E4 settings page DnD.
  // -----------------------------------------------------------------------
  function bindShareMintTriggers() {
    var triggers = document.querySelectorAll("[data-rmc-assist-share-mint-trigger]");
    if (!triggers.length) return;
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].addEventListener("click", handleShareMintClick);
    }
  }

  function handleShareMintClick(ev) {
    var trigger = ev.currentTarget;
    var holder = trigger.closest("[data-rmc-assist-share-mint]");
    if (!holder) return;
    var target = holder.getAttribute("data-rmc-assist-share-target") || "";
    var mintUrl = holder.getAttribute("data-rmc-assist-share-mint-url") || dockUrl("share_mint", "/assist-dock/share/mint/");
    trigger.disabled = true;
    fetch(mintUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({ target: target, ttl_hours: 24 }),
    })
      .then(function (r) { return r.json().then(function (b) { b.status = r.status; return b; }); })
      .then(function (payload) {
        var result = holder.querySelector("[data-rmc-assist-share-mint-result]");
        var output = holder.querySelector("[data-rmc-assist-share-mint-result] input");
        var expires = holder.querySelector("[data-rmc-assist-share-mint-expires]");
        if (!payload.ok) {
          if (result) result.hidden = false;
          if (output) output.value = "Mint failed: " + (payload.error || "unknown");
          if (expires) expires.textContent = "";
          return;
        }
        if (result) result.hidden = false;
        if (output) output.value = payload.short_url || "";
        if (expires) {
          expires.textContent = payload.expires_at ? "Expires " + payload.expires_at : "";
        }
      })
      .catch(function () {
        var result = holder.querySelector("[data-rmc-assist-share-mint-result]");
        var output = holder.querySelector("[data-rmc-assist-share-mint-result] input");
        if (result) result.hidden = false;
        if (output) output.value = "Mint failed: network error";
      })
      .finally(function () { trigger.disabled = false; });
  }

  function bindSettingsForm() {
    var form = document.getElementById("rmc-dock-settings-form");
    if (!form) return;
    var list = document.getElementById("rmc-dock-settings-chip-list");
    if (list) wireSettingsDragAndDrop(list);
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      saveSettings(form);
    });
  }

  function wireSettingsDragAndDrop(list) {
    var dragging = null;
    Array.prototype.forEach.call(list.querySelectorAll("[data-rmc-dock-slot-id]"), function (row) {
      row.addEventListener("dragstart", function () {
        dragging = row;
        row.classList.add("rmc-assist-settings__chip-row--dragging");
      });
      row.addEventListener("dragend", function () {
        if (dragging) dragging.classList.remove("rmc-assist-settings__chip-row--dragging");
        dragging = null;
      });
      row.addEventListener("dragover", function (ev) {
        ev.preventDefault();
        if (!dragging || dragging === row) return;
        var rect = row.getBoundingClientRect();
        var midpoint = rect.top + rect.height / 2;
        if (ev.clientY < midpoint) {
          row.parentNode.insertBefore(dragging, row);
        } else {
          row.parentNode.insertBefore(dragging, row.nextSibling);
        }
      });
    });
  }

  function saveSettings(form) {
    var status = document.getElementById("rmc-dock-settings-status");
    var list = document.getElementById("rmc-dock-settings-chip-list");
    var prefsUrl = form.getAttribute("data-rmc-dock-prefs-url") || dockUrl("prefs", "/assist-dock/prefs.json");
    var pinnedOrder = [];
    if (list) {
      Array.prototype.forEach.call(list.querySelectorAll("[data-rmc-dock-slot-id]"), function (row) {
        pinnedOrder.push(row.getAttribute("data-rmc-dock-slot-id"));
      });
    }
    var hidden = [];
    Array.prototype.forEach.call(form.querySelectorAll('input[name="hidden_slots[]"]:checked'), function (cb) {
      hidden.push(cb.value);
    });
    var density = (form.querySelector('input[name="density"]:checked') || {}).value || "cozy";
    var side = (form.querySelector('input[name="side"]:checked') || {}).value || "right";
    var halo = !!(form.querySelector('input[name="halo_enabled"]') || {}).checked;
    var voice = !!(form.querySelector('input[name="voice_enabled"]') || {}).checked;
    var payload = {
      pinned_order: pinnedOrder,
      hidden_slots: hidden,
      density: density,
      side: side,
      halo_enabled: halo,
      voice_enabled: voice,
    };
    if (status) status.textContent = "Saving…";
    fetch(prefsUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (r) { return r.json().then(function (b) { b.status = r.status; return b; }); })
      .then(function (body) {
        if (status) {
          status.textContent = body.saved ? "Saved." : "Save failed.";
        }
      })
      .catch(function () {
        if (status) status.textContent = "Save failed.";
      });
  }

  // -----------------------------------------------------------------------
  // Wave F2 — wave-at handler (presence landing).
  // -----------------------------------------------------------------------
  function bindWaveButtons() {
    var list = document.querySelector("[data-rmc-presence-list]");
    if (!list) return;
    var page = list.getAttribute("data-rmc-presence-page") || "/";
    var url = list.getAttribute("data-rmc-wave-url") || dockUrl("wave", "/assist-dock/wave/");
    var status = document.querySelector("[data-rmc-wave-status]");
    list.addEventListener("click", function (ev) {
      var btn = ev.target.closest("[data-rmc-wave-trigger]");
      if (!btn) return;
      var target = parseInt(btn.getAttribute("data-rmc-wave-target") || "0", 10);
      if (!target) return;
      btn.disabled = true;
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ target_user_id: target, page_path: page }),
      })
        .then(function (r) {
          return r.json().then(function (b) {
            b.status = r.status;
            return b;
          });
        })
        .then(function (envelope) {
          if (status) {
            if (envelope.ok) {
              status.textContent = "Wave sent.";
            } else if (envelope.error === "rate_limited") {
              status.textContent =
                "Slow down — wait " +
                (envelope.retry_after_seconds || 30) +
                "s before waving again.";
            } else {
              status.textContent = "Wave failed: " + (envelope.error || envelope.status);
            }
          }
        })
        .catch(function () {
          if (status) status.textContent = "Wave failed: network error.";
        })
        .finally(function () {
          setTimeout(function () { btn.disabled = false; }, 1500);
        });
    });
  }

  // -----------------------------------------------------------------------
  // Wave F4 — share recipient picker (mint + email).
  // -----------------------------------------------------------------------
  function bindShareRecipientPicker() {
    var triggers = document.querySelectorAll("[data-rmc-assist-share-recip-trigger]");
    for (var i = 0; i < triggers.length; i++) {
      triggers[i].addEventListener("click", handleShareRecipientClick);
    }
  }

  function handleShareRecipientClick(ev) {
    var trigger = ev.currentTarget;
    var holder = trigger.closest("[data-rmc-assist-share-recipients]");
    if (!holder) return;
    var target = holder.getAttribute("data-rmc-assist-share-target") || "";
    var url = holder.getAttribute("data-rmc-assist-share-recip-url") || dockUrl("share_mint_and_email", "/assist-dock/share/mint-and-email/");
    var textarea = holder.querySelector("#rmc-assist-share-recipients");
    var noteInput = holder.querySelector("#rmc-assist-share-note");
    var raw = textarea ? textarea.value : "";
    var recipients = raw
      .split(/[,;\n]+/)
      .map(function (s) { return (s || "").trim(); })
      .filter(function (s) { return s.length > 0; });
    if (!recipients.length) {
      var s = holder.querySelector("[data-rmc-assist-share-recip-status]");
      if (s) s.textContent = "Enter at least one address.";
      return;
    }
    trigger.disabled = true;
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({
        target: target,
        ttl_hours: 24,
        recipients: recipients,
        note: noteInput ? noteInput.value : "",
      }),
    })
      .then(function (r) { return r.json().then(function (b) { b.status = r.status; return b; }); })
      .then(function (envelope) {
        var result = holder.querySelector("[data-rmc-assist-share-recip-result]");
        var status = holder.querySelector("[data-rmc-assist-share-recip-status]");
        var list = holder.querySelector("[data-rmc-assist-share-recip-list]");
        if (result) result.hidden = false;
        if (!envelope.ok) {
          if (status) status.textContent = "Send failed: " + (envelope.error || envelope.status);
          if (list) list.innerHTML = "";
          return;
        }
        if (status) {
          status.textContent =
            "Sent to " + envelope.sent_count + " of " + envelope.recipients.length + " recipient(s).";
        }
        if (list) {
          list.innerHTML = "";
          envelope.recipients.forEach(function (r) {
            var li = document.createElement("li");
            li.textContent = r.address + " — " + r.send_status;
            list.appendChild(li);
          });
        }
      })
      .catch(function () {
        var status = holder.querySelector("[data-rmc-assist-share-recip-status]");
        if (status) status.textContent = "Send failed: network error.";
      })
      .finally(function () { trigger.disabled = false; });
  }

  // -----------------------------------------------------------------------
  // Wave F3 — translate landing writes locale_preference back to prefs.
  // Picking a language also POSTs the prefs endpoint with the chosen code.
  // -----------------------------------------------------------------------
  function bindTranslatePersistence() {
    var form = document.querySelector("[data-rmc-translate-form]");
    if (!form) return;
    var prefsUrl = form.getAttribute("data-rmc-translate-prefs-url") || dockUrl("prefs", "/assist-dock/prefs.json");
    form.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[name='language']");
      if (!btn) return;
      var code = btn.getAttribute("value") || "";
      if (!code) return;
      // Fire-and-forget; the form submit still hits set_language so the
      // immediate request also flips locale.
      fetch(prefsUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ locale_preference: code }),
        keepalive: true,
      }).catch(function () {});
    });
    var clearBtn = form.querySelector("[data-rmc-translate-clear]");
    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        fetch(prefsUrl, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(),
          },
          body: JSON.stringify({ locale_preference: "" }),
        })
          .then(function () { location.reload(); })
          .catch(function () {});
      });
    }
  }

  // -----------------------------------------------------------------------
  // Wave G1 — pseudo-cobrowse cursor throttled at 4 Hz with peer dot render.
  // Not WebSocket. Honest functional adequacy for school-admin use.
  // -----------------------------------------------------------------------
  var CURSOR_THROTTLE_MS = 250;
  var CURSOR_LIST_POLL_MS = 1500;
  var _cursorLastSent = 0;
  var _cursorLayer = null;
  var _cursorPeerNodes = {};
  var _cursorPollTimer = null;

  function ensureCursorLayer() {
    if (_cursorLayer && document.body.contains(_cursorLayer)) return _cursorLayer;
    _cursorLayer = document.createElement("div");
    _cursorLayer.className = "rmc-assist-cursor-layer";
    _cursorLayer.setAttribute("data-rmc-assist-cursor-layer", "1");
    _cursorLayer.setAttribute("aria-hidden", "true");
    _cursorLayer.style.position = "fixed";
    _cursorLayer.style.inset = "0";
    _cursorLayer.style.pointerEvents = "none";
    _cursorLayer.style.zIndex = "9998";
    document.body.appendChild(_cursorLayer);
    return _cursorLayer;
  }

  function renderPeerCursor(ping) {
    var layer = ensureCursorLayer();
    var node = _cursorPeerNodes[ping.user_id];
    if (!node) {
      node = document.createElement("div");
      node.className = "rmc-assist-cursor-peer";
      node.style.position = "absolute";
      node.style.width = "12px";
      node.style.height = "12px";
      node.style.borderRadius = "50%";
      node.style.border = "2px solid white";
      node.style.boxShadow = "0 1px 3px rgba(0,0,0,0.3)";
      node.style.transform = "translate(-50%, -50%)";
      node.style.transition = "left 0.2s ease, top 0.2s ease";
      var label = document.createElement("span");
      label.className = "rmc-assist-cursor-peer-label";
      label.style.position = "absolute";
      label.style.left = "12px";
      label.style.top = "12px";
      label.style.fontSize = "10px";
      label.style.padding = "2px 4px";
      label.style.borderRadius = "3px";
      label.style.background = "rgba(0,0,0,0.7)";
      label.style.color = "white";
      label.style.whiteSpace = "nowrap";
      node.appendChild(label);
      layer.appendChild(node);
      _cursorPeerNodes[ping.user_id] = node;
    }
    var hue = ping.color_hash || 0;
    node.style.background = "hsl(" + hue + ", 70%, 55%)";
    node.style.left = ping.x_pct + "%";
    node.style.top = ping.y_pct + "%";
    var label = node.querySelector(".rmc-assist-cursor-peer-label");
    if (label) {
      var text = ping.display_name || ("User " + ping.user_id);
      if (ping.selection_text) text += " — \"" + ping.selection_text + "\"";
      label.textContent = text;
    }
  }

  function dropPeerCursor(userId) {
    var node = _cursorPeerNodes[userId];
    if (node && node.parentNode) node.parentNode.removeChild(node);
    delete _cursorPeerNodes[userId];
  }

  function sendCursorHeartbeat(x, y, selection) {
    var now = Date.now();
    if (now - _cursorLastSent < CURSOR_THROTTLE_MS) return;
    _cursorLastSent = now;
    var url = dockUrl("cursor_heartbeat", "/assist-dock/cursors/heartbeat/");
    var page = (location && location.pathname) || "/";
    var w = Math.max(window.innerWidth || 1, 1);
    var h = Math.max(window.innerHeight || 1, 1);
    var body = {
      page_path: page,
      x_pct: Math.max(0, Math.min(100, (x / w) * 100)),
      y_pct: Math.max(0, Math.min(100, (y / h) * 100)),
      selection_text: selection || "",
    };
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(function () {});
  }

  function pollPeerCursors() {
    var url = dockUrl("cursor_list", "/assist-dock/cursors/list.json");
    var page = (location && location.pathname) || "/";
    fetch(url + "?page=" + encodeURIComponent(page), {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) { return r.json(); })
      .then(function (envelope) {
        var seen = {};
        (envelope.cursors || []).forEach(function (ping) {
          seen[ping.user_id] = true;
          renderPeerCursor(ping);
        });
        Object.keys(_cursorPeerNodes).forEach(function (uid) {
          if (!seen[uid]) dropPeerCursor(uid);
        });
      })
      .catch(function () {});
  }

  function startCursors() {
    if (isAuthLanding() || _authRealtimeStopped) return;
    if (document.body.dataset.rmcAssistCursors === "off") return;
    if (!document.body.classList.contains("authenticated") &&
        !document.querySelector("[data-rmc-authenticated]")) {
      return;
    }
    document.addEventListener("mousemove", function (ev) {
      var sel = "";
      try { sel = String((window.getSelection && window.getSelection().toString()) || "").slice(0, 200); }
      catch (_e) {}
      sendCursorHeartbeat(ev.clientX, ev.clientY, sel);
    }, { passive: true });
    if (_cursorPollTimer) clearInterval(_cursorPollTimer);
    _cursorPollTimer = setInterval(pollPeerCursors, CURSOR_LIST_POLL_MS);
    document.addEventListener("visibilitychange", function () {
      if (document.hidden && _cursorPollTimer) {
        clearInterval(_cursorPollTimer);
        _cursorPollTimer = null;
      } else if (!document.hidden && !_cursorPollTimer) {
        _cursorPollTimer = setInterval(pollPeerCursors, CURSOR_LIST_POLL_MS);
      }
    });
  }

  // -----------------------------------------------------------------------
  // Wave G2 — impersonation picker form bindings.
  // -----------------------------------------------------------------------
  function bindImpersonationPicker() {
    var form = document.querySelector("[data-rmc-impersonation-request-form]");
    if (form) {
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var url = form.getAttribute("action") || dockUrl("impersonation_request", "/assist-dock/impersonation/request/");
        var statusEl = document.querySelector("[data-rmc-impersonation-request-status]");
        var body = {
          target_user_id: parseInt(form.querySelector("#rmc-imp-target").value || "0", 10),
          reason: form.querySelector("#rmc-imp-reason").value || "",
          ttl_seconds: parseInt(form.querySelector("#rmc-imp-ttl").value || "0", 10),
        };
        fetch(url, {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-CSRFToken": csrfToken(),
          },
          body: JSON.stringify(body),
        })
          .then(function (r) { return r.json().then(function (b) { b.status = r.status; return b; }); })
          .then(function (envelope) {
            if (envelope.ok) {
              if (statusEl) statusEl.textContent = "Requested grant #" + envelope.grant_id + " — awaiting approval.";
              setTimeout(function () { location.reload(); }, 800);
            } else if (statusEl) {
              statusEl.textContent = "Request failed: " + (envelope.error || envelope.status);
            }
          })
          .catch(function () {
            if (statusEl) statusEl.textContent = "Request failed: network error.";
          });
      });
    }
    document.body.addEventListener("click", function (ev) {
      var t = ev.target;
      var action = null;
      var grantId = null;
      if (t.matches("[data-rmc-impersonation-approve]")) {
        action = "approve";
        grantId = t.getAttribute("data-rmc-impersonation-approve");
      } else if (t.matches("[data-rmc-impersonation-revoke]")) {
        action = "revoke";
        grantId = t.getAttribute("data-rmc-impersonation-revoke");
      } else if (t.matches("[data-rmc-impersonation-start]")) {
        action = "start";
        grantId = t.getAttribute("data-rmc-impersonation-start");
      } else {
        return;
      }
      ev.preventDefault();
      var url = dockUrl("impersonation_" + action, "/assist-dock/impersonation/" + action + "/");
      t.disabled = true;
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        body: JSON.stringify({ grant_id: parseInt(grantId, 10) }),
      })
        .then(function (r) { return r.json().then(function (b) { b.status = r.status; return b; }); })
        .then(function (envelope) {
          if (envelope.ok) {
            if (action === "start") {
              // Reload root so the impersonated identity takes effect.
              location.href = "/";
            } else {
              location.reload();
            }
          } else {
            alert("Impersonation " + action + " failed: " + (envelope.error || envelope.status));
            t.disabled = false;
          }
        })
        .catch(function () {
          alert("Impersonation " + action + " failed: network error.");
          t.disabled = false;
        });
    });
  }

  // Expose Wave B + C + D + E + F + G controls on the namespace.
  window.RMCAssistDock = window.RMCAssistDock || {};
  window.RMCAssistDock.fetchContext = fetchContext;
  window.RMCAssistDock.applyBadges = applyBadges;
  window.RMCAssistDock.applyHalo = applyHalo;
  window.RMCAssistDock.recordChipClick = recordChipClick;
  window.RMCAssistDock.pickHaloSlot = pickHaloSlot;
  window.RMCAssistDock.mountRegistryChips = mountRegistryChips;
  window.RMCAssistDock.runAIAction = runAIAction;
  window.RMCAssistDock.listInsights = listInsights;
  window.RMCAssistDock.clearInsight = clearInsight;
  window.RMCAssistDock.sendPresenceHeartbeat = sendPresenceHeartbeat;
  window.RMCAssistDock.startSSE = startSSE;
  window.RMCAssistDock.bindShareMintTriggers = bindShareMintTriggers;
  window.RMCAssistDock.bindSettingsForm = bindSettingsForm;
  window.RMCAssistDock.bindWaveButtons = bindWaveButtons;
  window.RMCAssistDock.bindShareRecipientPicker = bindShareRecipientPicker;
  window.RMCAssistDock.bindTranslatePersistence = bindTranslatePersistence;
  window.RMCAssistDock.startCursors = startCursors;
  window.RMCAssistDock.sendCursorHeartbeat = sendCursorHeartbeat;
  window.RMCAssistDock.bindImpersonationPicker = bindImpersonationPicker;

  function isAuthLanding() {
    return !!document.querySelector("[data-rmc-auth-landing]");
  }

  function init() {
    if (isAuthLanding()) return;
    if (document.body.dataset.rmcAssistDock === "off") return;
    mountDock(labels());
    // Wave A: annotate adopted nodes with their registry slot ids so the
    // dock chrome carries the SOT slug. Runs after mountDock so the
    // re-parented nodes get the attribute too.
    try {
      annotateAdoptedSlots();
    } catch (_e) {
      /* annotation is best-effort; never break dock mount */
    }
    // Wave B: bind click tracker, apply halo from local history, then
    // begin polling for live badges + quick actions. Skip when the
    // registry island is absent (anonymous shells / opt-out body attr).
    if (!registry()) {
      // Wave E + F + G mount points still need to bind on pages without the
      // registry island (e.g. the standalone landing pages).
      try {
        bindShareMintTriggers();
        bindSettingsForm();
        bindWaveButtons();
        bindShareRecipientPicker();
        bindTranslatePersistence();
        bindImpersonationPicker();
      } catch (_e) {}
      return;
    }
    try {
      // Wave C: paint registry-source chips (anchors / buttons) AFTER the
      // dom-adopt mount so they sit alongside the legacy widgets.
      mountRegistryChips();
      bindClickTracking();
      applyHalo();
      // Wave E1: presence heartbeat.
      startPresence();
      // Wave E3: try SSE first; fall back to poll only on repeated error.
      if (!startSSE()) {
        startPolling();
      }
      var _assistDockPageKey = pageKey();
      function refreshAssistDockForNavigation() {
        var next = pageKey();
        if (next === _assistDockPageKey) return;
        _assistDockPageKey = next;
        fetchContext();
      }
      window.addEventListener("popstate", refreshAssistDockForNavigation);
      document.addEventListener("htmx:afterSettle", refreshAssistDockForNavigation);
      document.addEventListener("rmc-soft-navigation", refreshAssistDockForNavigation);
      // Wave E4 + E5: bind settings DnD + share mint on the relevant pages.
      bindShareMintTriggers();
      bindSettingsForm();
      // Wave F2 + F3 + F4: presence wave / locale persistence / share recipients.
      bindWaveButtons();
      bindShareRecipientPicker();
      bindTranslatePersistence();
      // Wave G1 + G2: pseudo-cobrowse cursors + impersonation picker bindings.
      startCursors();
      bindImpersonationPicker();
    } catch (_e) {
      /* never break the dock if the context layer fails */
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
