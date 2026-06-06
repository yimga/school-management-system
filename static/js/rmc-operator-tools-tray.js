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
    var el =
      document.getElementById("page-data-rmc-operator-tools") ||
      document.getElementById("page-data-rmc-tenant-tools");
    if (!el) return null;
    try {
      var parsed = JSON.parse(el.textContent || "null");
      return parsed && parsed.enabled ? parsed : null;
    } catch (_e) {
      return null;
    }
  }

  function isTenantToolsConfig() {
    return !!document.getElementById("page-data-rmc-tenant-tools");
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
    if (!readConfig()) return false;
    if (isAuthLanding()) return false;
    if (!document.querySelector("[data-rmc-tools-tray-context]")) return false;
    if (isTenantToolsConfig()) {
      if (
        document.body.classList.contains("manager-portal-bridge") ||
        document.body.getAttribute("data-rmc-nav-bridge-host") === "manager"
      ) {
        return false;
      }
      return true;
    }
    return (
      document.documentElement.getAttribute("data-surface") === "control-plane" ||
      document.body.classList.contains("control-plane-shell") ||
      document.body.classList.contains("admin-manager-shell") ||
      document.body.classList.contains("manager-portal-bridge") ||
      document.body.getAttribute("data-rmc-nav-bridge-host") === "manager"
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

  // A structural / layout container that must NEVER be reparented into the
  // tray. An adopted chip (e.g. #back-to-top-btn) can be relocated by its own
  // JS into the canvas scroll container; without this guard findSlotWrap would
  // climb to #cp-main-content and the entire admin page would be moved inside
  // the hidden tray (the v4.02.x blank-admin bug). Defense-in-depth for every
  // DOM-adopted slot, not just back-to-top.
  function isUnmovableHost(el) {
    if (!el || el.nodeType !== 1) return true;
    var tag = el.tagName ? el.tagName.toLowerCase() : "";
    if (tag === "main" || tag === "body" || tag === "html") return true;
    if (
      el.id === "content" ||
      el.id === "cp-main-content" ||
      el.id === "content-main"
    ) {
      return true;
    }
    if (
      el.matches &&
      el.matches(
        ".rmc-app-shell, .rmc-app-shell__canvas, .rmc-app-shell__canvas-body, " +
          ".cp-page-body, .cp-admin-canvas-main, .cp-admin-page-body, " +
          "[data-rmc-cp-scroll], [data-rmc-scroll-container]"
      )
    ) {
      return true;
    }
    return false;
  }

  function findSlotWrap(chip) {
    if (!chip) return null;
    var slot = chip.closest(".rmc-assist-dock__slot");
    if (slot && !isUnmovableHost(slot)) return slot;
    var parent = chip.parentElement;
    // Refuse to treat a layout container as a movable slot wrapper — wrapping
    // the chip alone (handled by the caller) is always safe.
    if (!parent || isUnmovableHost(parent)) return null;
    return parent;
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

  // Build a navigable anchor chip (used for external slots and for dom-adopt
  // slots that fall back to a URL when their source node is absent).
  function buildAnchorChip(meta, href) {
    var el = document.createElement("a");
    el.href = href;
    el.className =
      "rmc-assist-dock__btn rmc-assist-dock__btn--" + (meta.id || "x");
    el.setAttribute("data-rmc-assist-slot-id", meta.id || "");
    if (meta.description) el.setAttribute("title", meta.description);
    el.innerHTML =
      '<i class="bi ' +
      escapeHtml(meta.icon || "bi-circle") +
      '" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
      escapeHtml(meta.label || "") +
      "</span>";
    return el;
  }

  // Resolve a URL fallback for a dom-adopt slot whose source node never
  // mounted on this surface (e.g. `messages` adopts `.portal-chathead`, which
  // only exists on tenant/portal shells — on the manager host there is no
  // chathead, so the chip must navigate to the inbox instead of dying).
  function domAdoptFallbackHref(slotId, urls) {
    if (slotId === "messages" && urls.messages && urls.messages !== "#") {
      return urls.messages;
    }
    return "";
  }

  // Dom-adopt slots whose bindTrayActions handler works WITHOUT the adopted
  // source node (ai-copilot toggles the copilot rail; help opens the rail/page
  // help). These must still render as buttons when their source is absent —
  // unlike context/feedback, which are inert without their adopted widget and
  // are skipped to avoid dead buttons.
  var DOM_ADOPT_BUTTON_FALLBACK = {
    "ai-copilot": true,
    help: true,
    "back-to-top": true,
  };

  function createTrayChip(slotId, reg, cfg) {
    var meta = slotMeta(slotId, reg);
    if (!meta) return null;
    var urls = (cfg && cfg.urls) || {};
    var btn;
    if (meta.source === "external" && meta.href) {
      btn = buildRegistryButton(meta, cfg);
    } else if (meta.source === "dom-adopt") {
      // We only reach createTrayChip when getChip() found no already-adopted
      // node — i.e. the adopted source never existed on this surface. Never
      // paint a dead button: render a real link when the slot has a URL
      // fallback, keep a plain button when the slot has a working handler that
      // doesn't need the adopted node, otherwise skip it so the tray shows
      // only controls that actually do something.
      var fallbackHref = domAdoptFallbackHref(slotId, urls);
      if (fallbackHref) {
        btn = buildAnchorChip(meta, fallbackHref);
      } else if (DOM_ADOPT_BUTTON_FALLBACK[slotId]) {
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
      } else {
        return null;
      }
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
    var chip = collectOrCreateChip(slotId, reg, cfg);
    if (!chip) return;
    // If the resolved "chip" is itself a structural container (e.g. an adopted
    // selector accidentally matched the canvas), never move it into the tray.
    if (isUnmovableHost(chip)) return;
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

  function resolvePagePlan(cfg) {
    var page = (cfg && cfg.page) || {};
    var plan = page.groups || {};
    return {
      order: plan.order || null,
      hide: plan.hide_groups || [],
      emphasize: plan.emphasize_groups || [],
    };
  }

  function groupOrder(cfg) {
    var plan = resolvePagePlan(cfg);
    if (plan.order && plan.order.length) {
      return plan.order;
    }
    return isTenantToolsConfig()
      ? ["primary", "page", "workspace", "actions"]
      : ["primary", "workflow", "page", "operator", "super", "actions"];
  }

  function renderPageHead(stack, cfg) {
    if (!stack) return;
    var page = (cfg && cfg.page) || {};
    var head = stack.querySelector("[data-rmc-tools-page-head]");
    if (!head) {
      head = document.createElement("header");
      head.className = "rmc-operator-tools__page-head";
      head.setAttribute("data-rmc-tools-page-head", "1");
      stack.insertBefore(head, stack.firstChild);
    }
    var title = page.title || "";
    if (!title && typeof document !== "undefined" && document.title) {
      title = document.title.replace(/\s*[|\-–—].*$/, "").trim();
    }
    if (!title) title = "Tools";
    var kind = page.dashboard_kind || "workspace";
    var kindLabel =
      kind === "landing" ? "Dashboard" : kind === "task" ? "Task" : "Page";
    if (page.surface === "admin") {
      kindLabel = kind === "landing" ? "Admin home" : "Admin";
    }
    var html =
      '<div class="rmc-operator-tools__page-head-inner">' +
      '<span class="rmc-operator-tools__page-kind" data-kind="' +
      escapeHtml(kind) +
      '">' +
      escapeHtml(kindLabel) +
      "</span>" +
      '<strong class="rmc-operator-tools__page-title">' +
      escapeHtml(title) +
      "</strong>";
    if (page.role && page.role !== "anonymous" && page.role !== "USER") {
      html +=
        '<span class="rmc-operator-tools__page-role">' +
        escapeHtml(page.role.replace(/_/g, " ")) +
        "</span>";
    }
    if (page.workflow_key) {
      html +=
        '<span class="rmc-operator-tools__page-workflow">' +
        escapeHtml(page.workflow_title || page.workflow_key) +
        "</span>";
    }
    html += "</div>";
    head.innerHTML = html;
  }

  function syncWorkflowChromeVisibility(stack, cfg) {
    if (!stack) return;
    var chrome = stack.querySelector(".rmc-workflow-auto-chrome");
    if (!chrome) return;
    var page = (cfg && cfg.page) || {};
    var hasStrip = !!chrome.querySelector(
      ".rmc-workflow-status-strip, .rmc-workflow-next-action, .rmc-workflow-help-panel"
    );
    chrome.hidden = !hasStrip && !page.workflow_key;
  }

  function renderPageQuickActions(host, cfg) {
    if (!host) return;
    var page = (cfg && cfg.page) || {};
    var actions = page.quick_actions || [];
    if (!actions.length) {
      host.innerHTML = "";
      host.hidden = true;
      return;
    }
    host.hidden = false;
    var html =
      '<span class="rmc-operator-tools__group-label">Page actions</span>' +
      '<div class="rmc-operator-tools__row">';
    for (var i = 0; i < actions.length; i++) {
      var a = actions[i];
      html +=
        '<a class="rmc-assist-dock__btn rmc-operator-tools__quick-action" href="' +
        escapeHtml(a.href || "#") +
        '" title="' +
        escapeHtml(a.description || a.label || "") +
        '"><i class="bi ' +
        escapeHtml(a.icon || "bi-lightning") +
        '" aria-hidden="true"></i><span class="rmc-assist-dock__label">' +
        escapeHtml(a.label || "") +
        "</span></a>";
    }
    html += "</div>";
    host.innerHTML = html;
  }

  function mountContextStack(trayBody, cfg) {
    var stack = document.querySelector("[data-rmc-tools-tray-context]");
    if (!stack || !trayBody) return false;
    stack.removeAttribute("hidden");
    stack.setAttribute("aria-hidden", "false");
    if (stack.parentNode !== trayBody) {
      trayBody.insertBefore(stack, trayBody.firstChild || null);
    }
    renderPageHead(stack, cfg);
    syncWorkflowChromeVisibility(stack, cfg);
    return !!(
      stack.querySelector(".rmc-cp-incident-banner") ||
      stack.querySelector(".rmc-workflow-auto-chrome") ||
      stack.querySelector("[data-rmc-wfp-tenant-trust]")
    );
  }

  function syncContextStackBadge(tab) {
    if (!tab) return;
    var stack = document.querySelector("[data-rmc-tools-tray-context]");
    if (!stack) return;
    var hasIncident = !!stack.querySelector(".rmc-cp-incident-banner");
    var hasWorkflow = !!stack.querySelector(".rmc-workflow-auto-chrome");
    var hasWorkflowPill = !!stack.querySelector(".rmc-operator-tools__page-workflow");
    var hasWfpInline = !!stack.querySelector("[data-rmc-wfp-inline]:not([hidden])");
    tab.setAttribute(
      "data-rmc-tools-context-available",
      hasIncident || hasWorkflow || hasWorkflowPill || hasWfpInline ? "1" : "0"
    );
    if (hasIncident) {
      tab.setAttribute("data-rmc-tools-context-incident", "1");
    } else {
      tab.removeAttribute("data-rmc-tools-context-incident");
    }
  }

  function buildTrayGroups(trayBody, cfg, reg) {
    var groups = cfg.groups || {};
    var labels = cfg.group_labels || {};
    var plan = resolvePagePlan(cfg);
    var order = groupOrder(cfg);
    for (var g = 0; g < order.length; g++) {
      var key = order[g];
      if (plan.hide.indexOf(key) >= 0) continue;
      var ids = groups[key];
      if (!ids || !ids.length) continue;
      var group = document.createElement("section");
      group.className = "rmc-operator-tools__group";
      if (plan.emphasize.indexOf(key) >= 0) {
        group.classList.add("rmc-operator-tools__group--emphasized");
      }
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

  function applyPageContext(cfg, trayBody, tab, reg) {
    if (!cfg) return;
    var stack = document.querySelector("[data-rmc-tools-tray-context]");
    renderPageHead(stack, cfg);
    syncWorkflowChromeVisibility(stack, cfg);
    var quickHost = trayBody
      ? trayBody.querySelector("[data-rmc-tools-page-quick-actions]")
      : null;
    if (quickHost) renderPageQuickActions(quickHost, cfg);
    var groupsHost = trayBody
      ? trayBody.querySelector("[data-rmc-tools-tray-groups]")
      : null;
    if (groupsHost) {
      groupsHost.innerHTML = "";
      buildTrayGroups(groupsHost, cfg, reg);
    }
    syncContextStackBadge(tab);
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
    if (messagesChip && messagesChip.tagName !== "A") {
      // An <a> chip (URL-fallback case from createTrayChip) navigates natively
      // — no handler needed. Otherwise the chip is either the adopted chathead
      // (let its own handler open the in-page panel) or a button that must be
      // routed to a real destination.
      messagesChip.addEventListener("click", function (ev) {
        // The adopted chathead carries its native click handler — defer to it.
        if (messagesChip.classList.contains("portal-chathead")) return;
        // A chathead mounted elsewhere on the page? Open it in place.
        var chathead = document.querySelector(".portal-chathead");
        if (chathead && chathead !== messagesChip) {
          ev.preventDefault();
          chathead.click();
          return;
        }
        // No in-page messages panel on this surface — go to the inbox.
        if (urls.messages && urls.messages !== "#") {
          ev.preventDefault();
          window.location.href = urls.messages;
        }
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
        var trigger = document.querySelector("[data-rmc-kbd-cheatsheet-trigger]");
        if (trigger) {
          trigger.click();
          return;
        }
        if (typeof window.cpShowShortcutsHelp === "function") {
          window.cpShowShortcutsHelp();
          return;
        }
        var legacy = document.getElementById("cpShowShortcutsHelp");
        if (legacy) legacy.click();
      });
    }

    var kb = getChip("tenant-kb");
    if (kb && urls.kb_home && urls.kb_home !== "#") {
      if (kb.tagName === "BUTTON") {
        kb.addEventListener("click", function () {
          window.location.href = urls.kb_home;
        });
      } else {
        kb.setAttribute("href", urls.kb_home);
      }
    }

    var support = getChip("tenant-support");
    if (support) {
      support.addEventListener("click", function (ev) {
        ev.preventDefault();
        var quick = document.querySelector("[data-rmc-support-quick-create]");
        if (quick) {
          quick.click();
          return;
        }
        if (window.RMCSupportQuickCreate && window.RMCSupportQuickCreate.open) {
          window.RMCSupportQuickCreate.open();
        }
      });
    }

    var search = getChip("command-search") || getChip("tenant-command");
    if (search) {
      search.addEventListener("click", function (ev) {
        ev.preventDefault();
        var cmdk = document.querySelector(
          "[data-rmc-cmdk-trigger], [data-rmc-command-palette-trigger], #studio-command-palette-btn"
        );
        if (cmdk) {
          cmdk.click();
          return;
        }
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
          return;
        }
        var tray = document.getElementById("rmcOperatorToolsTray");
        var tab = document.getElementById("rmcOperatorToolsTrayTab");
        if (tray && tab && tray.getAttribute("aria-hidden") !== "false") {
          tab.click();
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
    if (isTenantToolsConfig()) {
      document.body.setAttribute("data-rmc-workspace-tools", "tenant");
    } else {
      document.body.setAttribute("data-rmc-workspace-tools", "operator");
    }
    if (cfg.back_to_top_corner) {
      document.body.setAttribute("data-rmc-back-to-top-corner", cfg.back_to_top_corner);
    }
    document.documentElement.removeAttribute("data-rmc-back-to-top-policy");
    document.body.removeAttribute("data-rmc-back-to-top-policy");
  }

  function normalizeFilterText(value) {
    return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  // Type-to-filter for dense trays. Returns { apply, sync, focus, reset }.
  // The filter row sits between the tray header and the scrollable body so it
  // stays pinned while chips scroll. It only appears once the tray carries
  // enough chips to be worth filtering, and it hides empty groups + announces
  // the match count to assistive tech.
  function buildTrayFilter(tray, trayBody) {
    var head = tray.querySelector(".rmc-operator-tools__tray-head");
    var wrap = document.createElement("div");
    wrap.className = "rmc-operator-tools__filter";
    wrap.hidden = true;
    wrap.innerHTML =
      '<i class="bi bi-search rmc-operator-tools__filter-icon" aria-hidden="true"></i>' +
      '<input type="search" class="rmc-operator-tools__filter-input" ' +
      'data-rmc-tools-filter placeholder="' +
      escapeHtml("Filter tools…") +
      '" aria-label="' +
      escapeHtml("Filter tools") +
      '" autocomplete="off" spellcheck="false">' +
      '<span class="rmc-operator-tools__filter-status visually-hidden" ' +
      'data-rmc-tools-filter-status aria-live="polite"></span>';
    if (head && head.parentNode) {
      head.parentNode.insertBefore(wrap, head.nextSibling);
    } else {
      trayBody.insertBefore(wrap, trayBody.firstChild);
    }

    var input = wrap.querySelector("[data-rmc-tools-filter]");
    var status = wrap.querySelector("[data-rmc-tools-filter-status]");

    function allSlots() {
      return trayBody.querySelectorAll(".rmc-operator-tools__slot");
    }

    function apply(rawQuery) {
      var query = normalizeFilterText(
        rawQuery != null ? rawQuery : input ? input.value : ""
      );
      var slots = allSlots();
      var shown = 0;
      for (var i = 0; i < slots.length; i++) {
        var slot = slots[i];
        var match = true;
        if (query) {
          var labelEl = slot.querySelector(".rmc-assist-dock__label");
          var chipEl = slot.querySelector("[data-rmc-assist-slot-id]");
          var hay = normalizeFilterText(
            (labelEl ? labelEl.textContent : "") +
              " " +
              (chipEl ? chipEl.getAttribute("title") || "" : "") +
              " " +
              (chipEl ? chipEl.getAttribute("data-rmc-assist-slot-id") || "" : "")
          );
          match = hay.indexOf(query) !== -1;
        }
        slot.hidden = !match;
        if (match) shown++;
      }
      var groups = trayBody.querySelectorAll(".rmc-operator-tools__group");
      for (var g = 0; g < groups.length; g++) {
        var visible = groups[g].querySelectorAll(
          ".rmc-operator-tools__slot:not([hidden])"
        ).length;
        groups[g].hidden = query ? visible === 0 : false;
      }
      var none = trayBody.querySelector("[data-rmc-tools-filter-empty]");
      if (query && shown === 0) {
        if (!none) {
          none = document.createElement("p");
          none.className = "rmc-operator-tools__filter-empty";
          none.setAttribute("data-rmc-tools-filter-empty", "1");
          trayBody.appendChild(none);
        }
        none.hidden = false;
        none.textContent = "No tools match “" + query + "”.";
      } else if (none) {
        none.hidden = true;
      }
      if (status) {
        status.textContent = query
          ? shown + " tool" + (shown === 1 ? "" : "s") + " match"
          : "";
      }
    }

    function sync() {
      var count = allSlots().length;
      wrap.hidden = count < 7;
      if (wrap.hidden && input) input.value = "";
      apply(wrap.hidden ? "" : input ? input.value : "");
    }

    if (input) {
      input.addEventListener("input", function () {
        apply(input.value);
      });
      input.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          var firstChip = trayBody.querySelector(
            ".rmc-operator-tools__slot:not([hidden]) [data-rmc-assist-slot-id]"
          );
          if (firstChip) firstChip.click();
        } else if (ev.key === "Escape" && input.value) {
          // Clear the query first; only a second Escape (empty input) bubbles
          // up to the tray-close handler.
          ev.preventDefault();
          ev.stopPropagation();
          input.value = "";
          apply("");
        }
      });
    }

    return {
      apply: apply,
      sync: sync,
      focus: function () {
        if (input && !wrap.hidden) {
          try {
            input.focus();
            input.select();
          } catch (_e) {}
          return true;
        }
        return false;
      },
      reset: function () {
        if (input) input.value = "";
        apply("");
      },
    };
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
    var quickHost = document.createElement("div");
    quickHost.className = "rmc-operator-tools__page-quick";
    quickHost.setAttribute("data-rmc-tools-page-quick-actions", "1");
    quickHost.hidden = true;
    var groupsHost = document.createElement("div");
    groupsHost.className = "rmc-operator-tools__groups";
    groupsHost.setAttribute("data-rmc-tools-tray-groups", "1");
    trayBody.appendChild(quickHost);
    trayBody.appendChild(groupsHost);

    mountContextStack(trayBody, cfg);
    applyPageContext(cfg, trayBody, tab, reg);
    var trayFilter = buildTrayFilter(tray, trayBody);
    trayFilter.sync();
    integrateNotebook(cfg);
    bindTrayActions(cfg);
    syncContextStackBadge(tab);

    window.__rmcOperatorToolsCfg = cfg;
    window.__rmcToolsTrayRegistry = reg;

    window.addEventListener("rmc-assist-dock-context", function (ev) {
      var detail = ev.detail || {};
      if (detail.tools_tray && typeof detail.tools_tray === "object") {
        cfg.page = detail.tools_tray;
      }
      if (detail.quick_actions && cfg.page) {
        cfg.page.quick_actions = detail.quick_actions;
      }
      applyPageContext(cfg, trayBody, tab, reg);
      trayFilter.sync();
      syncEdgeTabBadge();
    });

    var closeBtn = tray.querySelector(".rmc-operator-tools__tray-close");
    function closeTray() {
      // Return focus to the edge tab if it was inside the tray, so keyboard
      // users aren't stranded on a now-hidden control.
      var focusWasInside =
        tray.contains(document.activeElement) && document.activeElement !== tab;
      tray.setAttribute("aria-hidden", "true");
      tab.setAttribute("aria-expanded", "false");
      dock.classList.remove("rmc-operator-tools--open");
      if (focusWasInside && typeof tab.focus === "function") {
        try {
          tab.focus();
        } catch (_e) {}
      }
    }
    function openTray() {
      tray.setAttribute("aria-hidden", "false");
      tab.setAttribute("aria-expanded", "true");
      dock.classList.add("rmc-operator-tools--open");
      syncEdgeTabBadge();
      // Move focus into the tray: the filter input when present, else the
      // first chip. Deferred a frame so the element is visible/focusable.
      window.requestAnimationFrame(function () {
        if (!trayFilter.focus()) {
          var firstChip = tray.querySelector(
            ".rmc-operator-tools__tray-body [data-rmc-assist-slot-id]"
          );
          if (firstChip && typeof firstChip.focus === "function") {
            try {
              firstChip.focus();
            } catch (_e) {}
          }
        }
      });
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

    document.addEventListener("rmc-tools-tray-page-sync", function (ev) {
      var detail = (ev && ev.detail) || {};
      if (detail.page && typeof detail.page === "object") {
        cfg.page = detail.page;
        applyPageContext(cfg, trayBody, tab, reg);
      }
    });

    document.addEventListener("rmc-wfp-inline-updated", function () {
      syncContextStackBadge(tab);
    });

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
