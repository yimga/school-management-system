/**
 * v4.02.0 — Operator Tools edge tab + horizontal tray.
 * Transforms the assist dock on control-plane into a consolidated Tools surface.
 */
(function () {
  "use strict";

  var TRANSFORMED = "data-rmc-operator-tools-transformed";
  var PANEL_NOTEBOOK = "notebook";
  var PANEL_SECTIONS = "sections";

  function readConfig() {
    var el = document.getElementById("page-data-rmc-operator-tools");
    if (!el) return null;
    try {
      var parsed = JSON.parse(el.textContent || "null");
      return parsed && parsed.enabled ? parsed : null;
    } catch (_e) {
      return null;
    }
  }

  function isAuthLanding() {
    if (document.querySelector("[data-rmc-auth-landing]")) return true;
    if (document.documentElement.getAttribute("data-rmc-auth-landing") === "1") {
      return true;
    }
    var shell = document.querySelector(".rmc-app-shell[data-rmc-auth-landing='1']");
    return !!shell;
  }

  function isOperatorToolsSurface() {
    if (!document.getElementById("page-data-rmc-operator-tools")) return false;
    if (isAuthLanding()) return false;
    return (
      document.documentElement.getAttribute("data-surface") === "control-plane" ||
      document.body.classList.contains("control-plane-shell") ||
      document.body.classList.contains("admin-manager-shell")
    );
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function getChip(slotId) {
    return document.querySelector(
      '[data-rmc-assist-slot-id="' + slotId.replace(/"/g, '\\"') + '"]'
    );
  }

  function findSlotWrap(chip) {
    if (!chip) return null;
    return chip.closest(".rmc-assist-dock__slot") || chip.parentElement;
  }

  function ensureRegistryChip(slotId, reg) {
    if (getChip(slotId)) return getChip(slotId);
    if (!reg || !Array.isArray(reg.slots)) return null;
    var slot = null;
    for (var i = 0; i < reg.slots.length; i++) {
      if (reg.slots[i].id === slotId) {
        slot = reg.slots[i];
        break;
      }
    }
    if (!slot) return null;
    if (window.RMCAssistDock && window.RMCAssistDock.mountRegistryChips) {
      window.RMCAssistDock.mountRegistryChips();
    }
    return getChip(slotId);
  }

  function buildRegistryButton(slot, cfg) {
    var el;
    var href = slot.href || "";
    if (slot.id === "platform-status" && cfg.urls && cfg.urls.platform_status) {
      href = cfg.urls.platform_status;
    }
    if (slot.source === "external" && href && href !== "#") {
      el = document.createElement("a");
      el.href = href;
    } else {
      el = document.createElement("button");
      el.type = "button";
    }
    el.className =
      "rmc-assist-dock__btn rmc-assist-dock__btn--" + (slot.id || "x");
    el.setAttribute("data-rmc-assist-slot-id", slot.id || "");
    if (slot.description) el.setAttribute("title", slot.description);
    el.innerHTML =
      '<i class="bi ' +
      escapeHtml(slot.icon || "bi-circle") +
      '" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
      escapeHtml(slot.label || "") +
      "</span>";
    return el;
  }

  function slotMeta(slotId, reg) {
    if (!reg || !Array.isArray(reg.slots)) return null;
    for (var i = 0; i < reg.slots.length; i++) {
      if (reg.slots[i].id === slotId) return reg.slots[i];
    }
    return null;
  }

  function createTrayChip(slotId, reg, cfg) {
    var meta = slotMeta(slotId, reg);
    if (!meta) return null;
    var btn;
    if (meta.source === "external" && meta.href) {
      btn = buildRegistryButton(meta, cfg);
    } else {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className =
        "rmc-assist-dock__btn rmc-assist-dock__btn--" + (slotId || "x");
      btn.setAttribute("data-rmc-assist-slot-id", slotId);
      if (meta.description) btn.setAttribute("title", meta.description);
      btn.innerHTML =
        '<i class="bi ' +
        escapeHtml(meta.icon || "bi-circle") +
        '" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
        escapeHtml(meta.label || "") +
        "</span>";
    }
    var wrap = document.createElement("div");
    wrap.className =
      "rmc-assist-dock__slot rmc-assist-dock__slot--" +
      slotId +
      " rmc-operator-tools__slot rmc-operator-tools__slot--" +
      slotId;
    wrap.appendChild(btn);
    return btn;
  }

  function collectOrCreateChip(slotId, reg, cfg) {
    var chip = getChip(slotId);
    if (chip) return chip;
    return createTrayChip(slotId, reg, cfg);
  }

  function moveChipToRow(row, slotId, reg, cfg) {
    if (cfg.workflow_header_only && slotId === "workflow-progress") {
      if (document.querySelector("[data-rmc-wfp-header-slot]")) {
        return;
      }
    }
    var chip = collectOrCreateChip(slotId, reg, cfg);
    if (!chip) return;
    var wrap = findSlotWrap(chip);
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className =
        "rmc-assist-dock__slot rmc-assist-dock__slot--" +
        slotId +
        " rmc-operator-tools__slot rmc-operator-tools__slot--" +
        slotId;
      wrap.appendChild(chip);
    }
    wrap.classList.add("rmc-operator-tools__slot", "rmc-operator-tools__slot--" + slotId);
    row.appendChild(wrap);
  }

  function buildTrayGroups(trayBody, cfg, reg) {
    var groups = cfg.groups || {};
    var labels = cfg.group_labels || {};
    var order = ["primary", "workflow", "page", "operator", "super", "actions"];
    for (var g = 0; g < order.length; g++) {
      var key = order[g];
      var ids = groups[key];
      if (!ids || !ids.length) continue;
      var group = document.createElement("section");
      group.className = "rmc-operator-tools__group";
      group.setAttribute("data-rmc-operator-tools-group", key);
      var label = document.createElement("span");
      label.className = "rmc-operator-tools__group-label";
      label.textContent = labels[key] || key;
      group.appendChild(label);
      var row = document.createElement("div");
      row.className = "rmc-operator-tools__row";
      for (var i = 0; i < ids.length; i++) {
        moveChipToRow(row, ids[i], reg, cfg);
      }
      if (!row.children.length) continue;
      group.appendChild(row);
      trayBody.appendChild(group);
    }
  }

  function bindTrayActions(cfg) {
    var urls = cfg.urls || {};
    var counts = cfg.counts || {};

    var aiChip = getChip("ai-copilot");
    if (aiChip) {
      aiChip.addEventListener("click", function (ev) {
        ev.preventDefault();
        var shell = document.querySelector(".rmc-app-shell");
        if (shell && shell.getAttribute("data-copilot") !== "expanded") {
          var toggle = document.querySelector("[data-rmc-copilot-toggle]");
          if (toggle) toggle.click();
          else shell.setAttribute("data-copilot", "expanded");
        }
        var chatTab = document.querySelector('[data-rmc-copilot-tab="chat"]');
        if (chatTab) chatTab.click();
      });
    }

    var helpChip = getChip("help");
    if (helpChip) {
      helpChip.addEventListener("click", function (ev) {
        ev.preventDefault();
        var railHelp = document.querySelector(
          ".rmc-app-shell__copilot [data-rmc-page-help], .lx-copilot__page-help"
        );
        if (railHelp) {
          railHelp.click();
          return;
        }
        if (window.rmcPageHelp && typeof window.rmcPageHelp.open === "function") {
          window.rmcPageHelp.open();
        }
      });
    }

    var messagesChip = getChip("messages");
    if (messagesChip) {
      messagesChip.addEventListener("click", function (ev) {
        if (messagesChip.getAttribute("data-rmc-assist-slot-id") === "messages") return;
        ev.preventDefault();
        // Target the registry-adopted messages slot, not the raw legacy node:
        // rmc-assist-dock.js stamps the chathead with this attribute on adopt.
        var chathead = document.querySelector('[data-rmc-assist-slot-id="messages"]');
        if (chathead) chathead.click();
      });
    }

    var nbChip = getChip("operator-notebook");
    if (nbChip) {
      nbChip.addEventListener("click", function (ev) {
        ev.preventDefault();
        togglePanel(PANEL_NOTEBOOK);
        var nb = document.querySelector("[data-rmc-operator-notebook]");
        if (nb) {
          nb.removeAttribute("data-rmc-notebook-tray-hidden");
          nb.setAttribute("data-rmc-notebook-state", "open");
        }
      });
    }

    var shortcuts = getChip("keyboard-shortcuts");
    if (shortcuts) {
      shortcuts.addEventListener("click", function (ev) {
        ev.preventDefault();
        var trigger = document.getElementById("cpShowShortcutsHelp");
        if (trigger) trigger.click();
      });
    }

    var search = getChip("command-search");
    if (search) {
      search.addEventListener("click", function (ev) {
        ev.preventDefault();
        var input = document.getElementById("cpSearchInput");
        if (input) {
          input.focus();
          input.select();
        } else if (window.rmcCommandBar && window.rmcCommandBar.open) {
          window.rmcCommandBar.open();
        }
      });
    }

    var copyLink = getChip("copy-page-link");
    if (copyLink) {
      copyLink.addEventListener("click", function (ev) {
        ev.preventDefault();
        var url = window.location.href;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(url).then(showCopyToast, fallbackCopy);
        } else {
          fallbackCopy();
        }
        function fallbackCopy() {
          var ta = document.createElement("textarea");
          ta.value = url;
          ta.setAttribute("readonly", "");
          ta.style.position = "fixed";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.select();
          try {
            document.execCommand("copy");
            showCopyToast();
          } catch (_e) {
            /* silent */
          }
          document.body.removeChild(ta);
        }
      });
    }

    var sectionsChip = getChip("on-this-page");
    if (sectionsChip) {
      sectionsChip.addEventListener("click", function (ev) {
        ev.preventDefault();
        togglePanel(PANEL_SECTIONS);
        renderSectionNav();
      });
    }

    var incidents = getChip("open-incidents");
    if (incidents && urls.incidents && urls.incidents !== "#") {
      if (incidents.tagName === "BUTTON") {
        incidents.addEventListener("click", function () {
          window.location.href = urls.incidents;
        });
      } else {
        incidents.setAttribute("href", urls.incidents);
      }
      if (counts.incidents > 0) {
        paintTrayBadge(incidents, counts.incidents, "warning");
      }
    }

    var security = getChip("security-posture");
    if (security && urls.security_posture && urls.security_posture !== "#") {
      if (security.tagName === "BUTTON") {
        security.addEventListener("click", function () {
          window.location.href = urls.security_posture;
        });
      } else {
        security.setAttribute("href", urls.security_posture);
      }
    }

    var activity = getChip("live-activity");
    if (activity) {
      activity.addEventListener("click", function (ev) {
        ev.preventDefault();
        var drawerId = urls.activity_drawer_id || "rmcCpActivityDrawer";
        var drawer = document.getElementById(drawerId);
        if (drawer && window.bootstrap && window.bootstrap.Offcanvas) {
          window.bootstrap.Offcanvas.getOrCreateInstance(drawer).show();
        }
      });
    }

    var cursors = getChip("live-cursors");
    if (cursors) {
      var cursorsOn = false;
      cursors.addEventListener("click", function (ev) {
        ev.preventDefault();
        cursorsOn = !cursorsOn;
        cursors.setAttribute("aria-pressed", cursorsOn ? "true" : "false");
        cursors.classList.toggle("rmc-assist-dock__btn--active", cursorsOn);
        if (cursorsOn && window.RMCAssistDock && window.RMCAssistDock.startCursors) {
          window.RMCAssistDock.startCursors();
        } else if (!cursorsOn && window.RMCAssistDock) {
          var layer = document.querySelector("[data-rmc-assist-cursor-layer]");
          if (layer && layer.parentNode) layer.parentNode.removeChild(layer);
        }
      });
    }

    var backTop = getChip("back-to-top");
    if (backTop) {
      backTop.addEventListener("click", function (ev) {
        ev.preventDefault();
        var btn = document.getElementById("back-to-top-btn");
        if (btn) btn.click();
      });
    }
  }

  function paintTrayBadge(chip, count, level) {
    if (!chip) return;
    var pill = chip.querySelector(".rmc-assist-dock__badge");
    if (!pill) {
      pill = document.createElement("span");
      pill.className = "rmc-assist-dock__badge";
      pill.setAttribute("aria-hidden", "true");
      chip.appendChild(pill);
    }
    pill.textContent = count > 99 ? "99+" : String(count);
    chip.setAttribute("data-rmc-badge-level", level || "info");
  }

  function showCopyToast() {
    var host = document.querySelector(".rmc-operator-tools__toast");
    if (!host) return;
    host.textContent = "Link copied";
    window.setTimeout(function () {
      host.textContent = "";
    }, 2000);
  }

  var activePanel = null;

  function togglePanel(id) {
    var panelNb = document.querySelector('[data-rmc-operator-tools-panel="' + PANEL_NOTEBOOK + '"]');
    var panelSec = document.querySelector('[data-rmc-operator-tools-panel="' + PANEL_SECTIONS + '"]');
    if (activePanel === id) {
      activePanel = null;
      if (panelNb) panelNb.hidden = true;
      if (panelSec) panelSec.hidden = true;
      var nb = document.querySelector("[data-rmc-operator-notebook]");
      if (nb) nb.setAttribute("data-rmc-notebook-tray-hidden", "1");
      return;
    }
    activePanel = id;
    if (panelNb) panelNb.hidden = id !== PANEL_NOTEBOOK;
    if (panelSec) panelSec.hidden = id !== PANEL_SECTIONS;
    if (id === PANEL_NOTEBOOK) {
      var notebook = document.querySelector("[data-rmc-operator-notebook]");
      if (notebook) notebook.removeAttribute("data-rmc-notebook-tray-hidden");
    }
  }

  function renderSectionNav() {
    var list = document.querySelector("[data-rmc-operator-tools-section-list]");
    if (!list) return;
    list.innerHTML = "";
    var anchors = document.querySelectorAll("[data-rmc-section-anchor], section[id]");
    var seen = {};
    var count = 0;
    for (var i = 0; i < anchors.length; i++) {
      var node = anchors[i];
      var id = node.id || node.getAttribute("href");
      if (!id || seen[id]) continue;
      if (node.matches && !node.matches("[id], [data-rmc-section-anchor]")) continue;
      var label =
        (node.getAttribute("data-rmc-section-label") ||
          node.getAttribute("aria-label") ||
          node.textContent ||
          id)
          .trim()
          .slice(0, 80);
      if (!label) continue;
      seen[id] = true;
      var link = document.createElement("a");
      link.href = "#" + id;
      link.textContent = label;
      link.setAttribute("data-rmc-section-anchor", "");
      list.appendChild(link);
      count++;
    }
    if (!count) {
      var empty = document.createElement("p");
      empty.className = "small text-muted mb-0";
      empty.textContent = "No sections on this page.";
      list.appendChild(empty);
    }
  }

  function integrateNotebook(cfg) {
    if (!cfg.tray_notebook) return;
    document.body.setAttribute("data-rmc-notebook-tray", "1");
    var notebook = document.querySelector("[data-rmc-operator-notebook]");
    if (!notebook) return;
    var panel = document.querySelector('[data-rmc-operator-tools-panel="' + PANEL_NOTEBOOK + '"]');
    if (!panel) return;
    notebook.setAttribute("data-rmc-notebook-tray-hidden", "1");
    notebook.setAttribute("data-rmc-notebook-state", "minimized");
    notebook.removeAttribute("data-rmc-notebook-draggable");
    panel.appendChild(notebook);
    if (cfg.hide_floating_notebook) {
      notebook.classList.add("lx-notebook--tray");
    }
  }

  function syncEdgeTabBadge() {
    var tabBadge = document.querySelector(".rmc-operator-tools__edge-tab-badge");
    if (!tabBadge) return;
    var total = 0;
    var chips = document.querySelectorAll(
      ".rmc-operator-tools__tray [data-rmc-badge-level]"
    );
    for (var i = 0; i < chips.length; i++) {
      var c = chips[i].getAttribute("data-rmc-badge-count");
      if (c) total += parseInt(c, 10) || 0;
      else total += 1;
    }
    if (total > 0) {
      tabBadge.hidden = false;
      tabBadge.textContent = total > 99 ? "99+" : String(total);
    } else {
      tabBadge.hidden = true;
    }
  }

  function applyLayoutAttrs(cfg) {
    document.body.setAttribute("data-rmc-assist-layout", "edge-tray");
    if (cfg.workflow_header_only) {
      document.body.setAttribute("data-rmc-wfp-header-only", "1");
    }
    if (cfg.back_to_top_corner) {
      document.body.setAttribute("data-rmc-back-to-top-corner", cfg.back_to_top_corner);
    }
    document.documentElement.removeAttribute("data-rmc-back-to-top-policy");
    document.body.removeAttribute("data-rmc-back-to-top-policy");
  }

  function transform(cfg) {
    var dock = document.querySelector(".rmc-assist-dock");
    if (!dock || dock.getAttribute(TRANSFORMED) === "1") return false;

    applyLayoutAttrs(cfg);

    var shell = document.createElement("div");
    shell.className = "rmc-operator-tools__shell";
    shell.setAttribute("data-rmc-operator-tools-shell", "1");

    var tray = document.createElement("aside");
    tray.className = "rmc-operator-tools__tray";
    tray.setAttribute("role", "dialog");
    tray.setAttribute("aria-modal", "false");
    tray.setAttribute("aria-hidden", "true");
    tray.setAttribute("aria-labelledby", "rmcOperatorToolsTrayTitle");
    tray.innerHTML =
      '<header class="rmc-operator-tools__tray-head">' +
      '<h2 class="rmc-operator-tools__tray-title" id="rmcOperatorToolsTrayTitle">' +
      escapeHtml(cfg.tab_label || "Tools") +
      "</h2>" +
      '<button type="button" class="rmc-operator-tools__tray-close" aria-label="Close">' +
      '<i class="bi bi-x-lg" aria-hidden="true"></i></button>' +
      "</header>" +
      '<div class="rmc-operator-tools__tray-body"></div>' +
      '<div class="rmc-operator-tools__toast" aria-live="polite"></div>' +
      '<div class="rmc-operator-tools__panel" data-rmc-operator-tools-panel="' +
      PANEL_NOTEBOOK +
      '" hidden></div>' +
      '<div class="rmc-operator-tools__panel" data-rmc-operator-tools-panel="' +
      PANEL_SECTIONS +
      '" hidden>' +
      '<nav class="rmc-operator-tools__section-nav" aria-label="On this page">' +
      '<div data-rmc-operator-tools-section-list></div></nav></div>';

    var tab = document.createElement("button");
    tab.type = "button";
    tab.className = "rmc-operator-tools__edge-tab";
    tab.setAttribute("aria-expanded", "false");
    tab.setAttribute("aria-controls", "rmcOperatorToolsTray");
    tab.id = "rmcOperatorToolsTrayTab";
    tray.id = "rmcOperatorToolsTray";
    tab.innerHTML =
      '<span class="rmc-operator-tools__edge-tab-badge" hidden aria-hidden="true">0</span>' +
      '<span class="rmc-operator-tools__edge-tab-label">' +
      escapeHtml(cfg.tab_label || "Tools") +
      "</span>";

    shell.appendChild(tray);
    shell.appendChild(tab);
    dock.appendChild(shell);

    var reg =
      window.RMCAssistDock && window.RMCAssistDock.registrySnapshot
        ? window.RMCAssistDock.registrySnapshot()
        : null;
    if (!reg) {
      var regEl = document.getElementById("page-data-rmc-assist-dock-registry");
      if (regEl) {
        try {
          reg = JSON.parse(regEl.textContent || "null");
        } catch (_e) {
          reg = null;
        }
      }
    }

    var trayBody = tray.querySelector(".rmc-operator-tools__tray-body");
    buildTrayGroups(trayBody, cfg, reg);
    integrateNotebook(cfg);
    bindTrayActions(cfg);

    var closeBtn = tray.querySelector(".rmc-operator-tools__tray-close");
    function closeTray() {
      tray.setAttribute("aria-hidden", "true");
      tab.setAttribute("aria-expanded", "false");
      dock.classList.remove("rmc-operator-tools--open");
    }
    function openTray() {
      tray.setAttribute("aria-hidden", "false");
      tab.setAttribute("aria-expanded", "true");
      dock.classList.add("rmc-operator-tools--open");
      syncEdgeTabBadge();
    }
    function toggleTray() {
      if (tab.getAttribute("aria-expanded") === "true") closeTray();
      else openTray();
    }

    tab.addEventListener("click", toggleTray);
    if (closeBtn) closeBtn.addEventListener("click", closeTray);

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && tab.getAttribute("aria-expanded") === "true") {
        closeTray();
      }
    });

    document.addEventListener("click", function (ev) {
      if (!tab.getAttribute("aria-expanded") || tab.getAttribute("aria-expanded") === "false") {
        return;
      }
      if (ev.target.closest(".rmc-operator-tools__shell")) return;
      closeTray();
    });

    window.addEventListener("rmc-assist-dock-context", syncEdgeTabBadge);

    dock.setAttribute(TRANSFORMED, "1");
    document.dispatchEvent(new CustomEvent("rmc-operator-tools-ready"));

    if (window.RMCAssistDock && window.RMCAssistDock.syncAssistRailMetrics) {
      window.RMCAssistDock.syncAssistRailMetrics();
    }
    if (window.RMCBackToTop && window.RMCBackToTop.refresh) {
      window.RMCBackToTop.refresh();
    }
    return true;
  }

  function init() {
    if (!isOperatorToolsSurface()) return;
    var cfg = readConfig();
    if (!cfg) return;

    function tryTransform() {
      if (!document.querySelector(".rmc-assist-dock")) return false;
      if (window.RMCAssistDock && window.RMCAssistDock.mountRegistryChips) {
        window.RMCAssistDock.mountRegistryChips();
      }
      return transform(cfg);
    }

    if (tryTransform()) return;

    document.addEventListener("rmc-assist-dock-mounted", function onMounted() {
      document.removeEventListener("rmc-assist-dock-mounted", onMounted);
      tryTransform();
    });
  }

  window.RMCOperatorTools = {
    readConfig: readConfig,
    transform: transform,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
