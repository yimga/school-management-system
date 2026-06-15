/**
 * Context Lens — manager copilot rail, tenant offcanvas sheet, floating AI copilot panel.
 */
(function () {
  "use strict";

  if (typeof document === "undefined") { return; }

  var MAX_PINS = 2;
  var PIN_KEY = "rmc-copilot-lens-pins";

  var PLAYBOOKS = {
    "operator-schools-roster": {
      eyebrow: "Schools command",
      empty: "Select a school row to preview lifecycle, sector, and one-tap operator moves.",
      chips: [
        "Which schools are frozen or in offboarding?",
        "Draft a check-in note for the selected school",
        "What should I verify before opening Tenant 360?",
      ],
    },
    "operator-team-roster": {
      eyebrow: "Operator identity",
      empty: "Select a teammate to review MFA posture and promotion paths without leaving the roster.",
      chips: [
        "Who still needs MFA enrollment?",
        "Explain tier vs platform scope for this operator",
        "Draft an invite follow-up for pending operators",
      ],
    },
    "operator-offboarding-queue": {
      eyebrow: "Offboarding command",
      empty: "Select a queued school to review purge schedule, billing clearance, and provisioning state.",
      chips: [
        "Which schools are due for purge today?",
        "Explain billing hold vs legal hold for this tenant",
        "What should I verify before applying scheduled purges?",
      ],
    },
    "operator-tenant-health": {
      eyebrow: "Tenant health",
      empty: "Select a school to review lifecycle, activity, and statutory posture with live provisioning chips.",
      chips: [
        "Which schools have missing statutory packs?",
        "Summarize inactive schools with no recent activity",
        "What should I check before approving this tenant?",
      ],
    },
    "operator-dashboard-fleet": {
      eyebrow: "Fleet command",
      empty: "Select a registry row or queue item to mirror provisioning and lifecycle in Lens.",
      chips: [
        "Which schools are stuck in provisioning?",
        "Explain the highest-risk tenants on this dashboard",
        "Draft operator next steps for the selected school",
      ],
    },
    "tenant-student-roster": {
      eyebrow: "Student roster",
      empty: "Select a student to see classroom, tags, and backend actions in the copilot lens.",
      chips: [
        "Summarize this student's status and classroom",
        "What tags should I review before parent night?",
        "Suggest next best action for this admission record",
      ],
    },
  };

  function lensRoots() {
    return document.querySelectorAll("[data-rmc-copilot-lens-root]");
  }

  function rail() {
    return document.querySelector("[data-rmc-copilot-rail]");
  }

  function pageLensKey() {
    var root = document.querySelector("[data-rmc-copilot-page-lens]");
    return root ? root.getAttribute("data-rmc-copilot-page-lens") || "" : "";
  }

  function playbook() {
    return PLAYBOOKS[pageLensKey()] || null;
  }

  function readPins() {
    try {
      var raw = window.localStorage.getItem(PIN_KEY);
      if (!raw) { return []; }
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed.slice(0, MAX_PINS) : [];
    } catch (_e) {
      return [];
    }
  }

  function writePins(pins) {
    try {
      window.localStorage.setItem(PIN_KEY, JSON.stringify(pins.slice(0, MAX_PINS)));
    } catch (_e) {}
  }

  function setRailTab(tab) {
    var node = rail();
    if (!node) { return; }
    node.setAttribute("data-rmc-copilot-active-tab", tab);
    var shell = document.querySelector(".rmc-app-shell[data-copilot], body[data-copilot]");
    if (shell) { shell.setAttribute("data-copilot", "expanded"); }
  }

  function openTenantLensChrome() {
    var panel = document.getElementById("aiCopilotPanel");
    var trigger = document.getElementById("aiCopilotTrigger");
    if (panel && panel.classList) {
      panel.classList.add("active");
      if (trigger) { trigger.setAttribute("aria-expanded", "true"); }
      var view = panel.querySelector("[data-ai-copilot-view-panel='lens']");
      if (view) { view.hidden = false; }
      var chat = panel.querySelector("[data-ai-copilot-view-panel='chat']");
      if (chat) { chat.hidden = true; }
      panel.querySelectorAll("[data-ai-copilot-view]").forEach(function (btn) {
        var on = btn.getAttribute("data-ai-copilot-view") === "lens";
        btn.classList.toggle("is-active", on);
        btn.setAttribute("aria-selected", on ? "true" : "false");
      });
      return;
    }
    var sheet = document.getElementById("rmcCopilotContextLensSheet");
    if (sheet && window.bootstrap && window.bootstrap.Offcanvas) {
      window.bootstrap.Offcanvas.getOrCreateInstance(sheet).show();
    }
  }

  function openLensChrome() {
    if (rail()) {
      setRailTab("lens");
    } else {
      openTenantLensChrome();
    }
  }

  function fillInput(text) {
    var input = document.querySelector("[data-rmc-copilot-input]") || document.getElementById("aiCopilotInput");
    if (!input) { return; }
    input.value = text;
    if (typeof input.focus === "function") { input.focus(); }
    if (!rail()) { openTenantLensChrome(); }
    else { setRailTab("chat"); }
  }

  function q(root, sel) {
    return root.querySelector(sel);
  }

  function lifecyclePillClass(value) {
    var text = String(value || "").toLowerCase();
    if (text.indexOf("active") >= 0 && text.indexOf("inactive") < 0) return "success";
    if (text.indexOf("offboard") >= 0 || text.indexOf("frozen") >= 0) return "danger";
    if (text.indexOf("schedul") >= 0 || text.indexOf("pending") >= 0 || text.indexOf("provision") >= 0) {
      return "warning";
    }
    return "muted";
  }

  function activePillClass(value) {
    return String(value || "").toLowerCase() === "yes" ? "success" : "secondary";
  }

  function metaKeyKind(key) {
    var lower = String(key || "").toLowerCase();
    if (lower === "active") return "active";
    if (lower === "lifecycle") return "lifecycle";
    return "";
  }

  function renderStatusPills(root, detail) {
    var host = q(root, "[data-rmc-copilot-lens-status]");
    if (!host) return;
    host.innerHTML = "";
    if (!detail || detail.bulkCount) {
      host.hidden = true;
      return;
    }
    var meta = detail.meta || {};
    var chips = [];
    Object.keys(meta).forEach(function (key) {
      var kind = metaKeyKind(key);
      if (kind === "active") {
        chips.push({ label: key, value: meta[key], tone: activePillClass(meta[key]) });
      } else if (kind === "lifecycle") {
        chips.push({ label: key, value: meta[key], tone: lifecyclePillClass(meta[key]) });
      }
    });
    if (!chips.length) {
      host.hidden = true;
      return;
    }
    chips.forEach(function (chip) {
      var span = document.createElement("span");
      span.className = "lx-copilot__lens-pill lx-copilot__lens-pill--" + chip.tone;
      span.textContent = chip.label + ": " + chip.value;
      host.appendChild(span);
    });
    host.hidden = false;
  }

  function setLensCardVisible(root, visible) {
    var card = q(root, "[data-rmc-copilot-lens-card]");
    if (card) card.hidden = !visible;
  }

  function dismissSelection() {
    if (typeof window.rmcRowDetailDismiss === "function") {
      window.rmcRowDetailDismiss();
      return;
    }
    try {
      document.dispatchEvent(new CustomEvent("rmc:row-detail-close", { bubbles: true }));
    } catch (_e) {}
  }

  function onRowDetailClose() {
    renderSelection(null);
    var sheet = document.getElementById("rmcCopilotContextLensSheet");
    if (sheet && window.bootstrap && window.bootstrap.Offcanvas) {
      var inst = window.bootstrap.Offcanvas.getInstance(sheet);
      if (inst) inst.hide();
    }
    document.querySelectorAll("tr[data-rmc-row-detail='1'].is-selected, [data-rmc-row-detail='1'].is-selected").forEach(function (row) {
      row.classList.remove("is-selected");
    });
  }

  function renderSelection(detail) {
    var roots = lensRoots();
    if (!roots.length) { return; }

    roots.forEach(function (root) {
      var titleEl = q(root, "[data-rmc-copilot-lens-title]");
      var subEl = q(root, "[data-rmc-copilot-lens-subtitle]");
      var metaEl = q(root, "[data-rmc-copilot-lens-meta]");
      var emptyEl = q(root, "[data-rmc-copilot-lens-empty]");
      if (!titleEl || !metaEl) { return; }

      if (!detail || (!detail.title && !detail.bulkCount)) {
        titleEl.textContent = "";
        if (subEl) { subEl.textContent = ""; }
        metaEl.innerHTML = "";
        setLensCardVisible(root, false);
        renderStatusPills(root, null);
        if (emptyEl) {
          var pb = playbook();
          emptyEl.textContent = pb ? pb.empty : "Select a row to mirror context here.";
          emptyEl.hidden = false;
        }
        var actionsWrap = q(root, "[data-rmc-copilot-lens-actions]");
        if (actionsWrap) { actionsWrap.innerHTML = ""; }
        return;
      }

      setLensCardVisible(root, true);
      if (emptyEl) { emptyEl.hidden = true; }

      if (detail.bulkCount) {
        titleEl.textContent = detail.bulkCount + " rows selected";
        if (subEl) { subEl.textContent = detail.summary || ""; }
        metaEl.innerHTML = "";
        renderStatusPills(root, detail);
        var bulkMeta = document.createElement("div");
        bulkMeta.className = "lx-copilot__lens-kv";
        bulkMeta.textContent = detail.summary || "";
        metaEl.appendChild(bulkMeta);
      } else {
        titleEl.textContent = detail.title || "";
        if (subEl) { subEl.textContent = detail.subtitle || ""; }
        metaEl.innerHTML = "";
        renderStatusPills(root, detail);
        var meta = detail.meta || {};
        Object.keys(meta).forEach(function (key) {
          if (metaKeyKind(key)) return;
          var row = document.createElement("div");
          row.className = "lx-copilot__lens-kv";
          var k = document.createElement("span");
          k.className = "lx-copilot__lens-k";
          k.textContent = key;
          var v = document.createElement("span");
          v.className = "lx-copilot__lens-v";
          v.textContent = String(meta[key] == null ? "—" : meta[key]);
          row.appendChild(k);
          row.appendChild(v);
          metaEl.appendChild(row);
        });
      }

      var actionsWrap = q(root, "[data-rmc-copilot-lens-actions]");
      if (actionsWrap) {
        actionsWrap.innerHTML = "";
        (detail.actions || []).forEach(function (act) {
          if (!act || !act.href) { return; }
          var a = document.createElement("a");
          a.className = "btn btn-sm " + (act.variant === "primary" ? "btn-primary" : "btn-outline-secondary");
          a.href = act.href;
          a.textContent = act.label || "Open";
          actionsWrap.appendChild(a);
        });
      }
    });

    var sel = document.querySelector("[data-rmc-copilot-rail-selection]");
    if (sel) {
      // detail is null on the empty/initial state (init() calls
      // renderSelection(null)). Without this guard, `detail.bulkCount` throws
      // "Cannot read properties of null", which aborts init() before
      // wireLensUi() and the row-detail/bulk-selection listeners are attached —
      // leaving the whole copilot context-lens dead on every page load.
      if (!detail) {
        sel.textContent = "";
      } else if (detail.bulkCount) {
        sel.textContent = detail.bulkCount + " selected";
      } else {
        sel.textContent = detail.title
          ? detail.title + (detail.subtitle ? " · " + detail.subtitle : "")
          : "";
      }
    }
  }

  function renderPins() {
    document.querySelectorAll("[data-rmc-copilot-lens-pins]").forEach(function (list) {
      var pins = readPins();
      list.innerHTML = "";
      if (!pins.length) {
        var li = document.createElement("li");
        li.className = "lx-copilot__lens-pin lx-copilot__lens-pin--empty";
        li.textContent = "Pin up to two rows to compare side-by-side.";
        list.appendChild(li);
        return;
      }
      pins.forEach(function (pin, idx) {
        var li = document.createElement("li");
        li.className = "lx-copilot__lens-pin";
        li.textContent = pin.title || "Row";
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "lx-copilot__lens-pin-remove";
        btn.setAttribute("aria-label", "Remove pin");
        btn.textContent = "×";
        btn.addEventListener("click", function () {
          var next = readPins().filter(function (_, i) { return i !== idx; });
          writePins(next);
          renderPins();
        });
        li.appendChild(btn);
        list.appendChild(li);
      });
    });
  }

  function renderPlaybookChips() {
    var pb = playbook();
    document.querySelectorAll("[data-rmc-copilot-lens-chips]").forEach(function (host) {
      host.innerHTML = "";
      if (!pb || !pb.chips) { return; }
      pb.chips.forEach(function (text) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "lx-copilot__lens-chip";
        btn.setAttribute("data-rmc-copilot-lens-chip", "1");
        btn.textContent = text;
        host.appendChild(btn);
      });
      var eyebrow = host.closest("[data-rmc-copilot-lens-root]")
        && host.closest("[data-rmc-copilot-lens-root]").querySelector("[data-rmc-copilot-lens-eyebrow]");
      if (eyebrow && pb.eyebrow) { eyebrow.textContent = pb.eyebrow; }
    });
  }

  function pinCurrent(detail) {
    if (!detail || !detail.title) { return; }
    var pins = readPins().filter(function (p) { return p.title !== detail.title; });
    pins.unshift({ title: detail.title, subtitle: detail.subtitle || "" });
    writePins(pins);
    renderPins();
    openLensChrome();
  }

  function onRowOpen(ev) {
    var detail = ev.detail || {};
    renderSelection(detail);
    openLensChrome();
    document.dispatchEvent(new CustomEvent("rmc:cockpit:context-changed", { bubbles: true }));
  }

  function onBulkChange(ev) {
    var d = ev.detail || {};
    if (!d.count) {
      renderSelection(null);
      return;
    }
    renderSelection({
      bulkCount: d.count,
      summary: d.summary || "",
      title: "",
      subtitle: "",
      meta: {},
      actions: [],
    });
    openLensChrome();
  }

  function wireLensUi() {
    document.querySelectorAll("[data-rmc-copilot-lens-pin]").forEach(function (pinBtn) {
      pinBtn.addEventListener("click", function () {
        var root = pinBtn.closest("[data-rmc-copilot-lens-root]");
        if (!root) { return; }
        var title = q(root, "[data-rmc-copilot-lens-title]");
        if (!title || !title.textContent) { return; }
        pinCurrent({
          title: title.textContent,
          subtitle: (q(root, "[data-rmc-copilot-lens-subtitle]") || {}).textContent || "",
        });
      });
    });
    document.querySelectorAll("[data-rmc-copilot-lens-ask]").forEach(function (askBtn) {
      askBtn.addEventListener("click", function () {
        var root = askBtn.closest("[data-rmc-copilot-lens-root]");
        if (!root) { return; }
        var title = q(root, "[data-rmc-copilot-lens-title]");
        if (!title || !title.textContent) { return; }
        fillInput("Tell me what matters about " + title.textContent + " on this page.");
      });
    });
    document.addEventListener("click", function (ev) {
      var chip = ev.target && ev.target.closest("[data-rmc-copilot-lens-chip]");
      if (chip) {
        ev.preventDefault();
        fillInput(chip.textContent.trim());
        return;
      }
      var dismiss = ev.target && ev.target.closest("[data-rmc-copilot-lens-dismiss]");
      if (dismiss) {
        ev.preventDefault();
        dismissSelection();
      }
    });
    document.addEventListener("keydown", function (ev) {
      if (ev.key !== "Escape" || ev.defaultPrevented) return;
      var card = document.querySelector("[data-rmc-copilot-lens-card]:not([hidden])");
      if (!card) return;
      dismissSelection();
    });
    document.addEventListener("rmc-workflow-copilot-context", function (ev) {
      var detail = ev.detail || window.__rmcWorkflowCopilotContext;
      if (!detail) { return; }
      var stuck = detail.stuck_count || 0;
      var degrading = detail.degrading_count || 0;
      var ids = (detail.active_run_ids || []).join(", ");
      var prompt =
        "Explain active platform workflows. Stuck: " +
        stuck +
        ", slowing: " +
        degrading +
        (ids ? ". Run ids: " + ids : "") +
        ". Suggest the next operator action.";
      fillInput(prompt);
      openLensChrome();
    });
    document.querySelectorAll("[data-ai-copilot-view]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var view = btn.getAttribute("data-ai-copilot-view");
        var panel = document.getElementById("aiCopilotPanel");
        if (!panel) { return; }
        panel.querySelectorAll("[data-ai-copilot-view-panel]").forEach(function (pane) {
          pane.hidden = pane.getAttribute("data-ai-copilot-view-panel") !== view;
        });
        panel.querySelectorAll("[data-ai-copilot-view]").forEach(function (b) {
          var on = b.getAttribute("data-ai-copilot-view") === view;
          b.classList.toggle("is-active", on);
          b.setAttribute("aria-selected", on ? "true" : "false");
        });
      });
    });
  }

  function init() {
    if (!lensRoots().length && !document.getElementById("rmcCopilotContextLensSheet")) { return; }
    renderPlaybookChips();
    renderPins();
    renderSelection(null);
    wireLensUi();
    document.addEventListener("rmc:row-detail-open", onRowOpen);
    document.addEventListener("rmc:row-detail-close", onRowDetailClose);
    document.addEventListener("rmc:bulk-selection-changed", onBulkChange);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
