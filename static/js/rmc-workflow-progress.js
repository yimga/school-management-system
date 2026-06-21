/**
 * RunMyCampus Workflow Progress Bus — frontend chip controller (v4.00.96).
 *
 * Architecture:
 * - Mounts a floating chip in the body. Connects to /platform/workflow-progress/stream/
 *   via EventSource. On every snapshot event, re-renders the expanded card with
 *   the step train + ETA + AI-suggested fix card when applicable.
 * - Gracefully degrades on no-EventSource environments by polling /badge/.
 * - Reduced-motion + small-screen friendly; full keyboard support (g w shortcut).
 */
(function () {
  "use strict";

  if (window.__rmcWorkflowProgressMounted) return;
  window.__rmcWorkflowProgressMounted = true;

  var ENDPOINT_STREAM = "/platform-runtime/workflow-progress/stream/";
  var ENDPOINT_ACTIVE = "/platform-runtime/workflow-progress/active/";
  var ENDPOINT_BADGE = "/platform-runtime/workflow-progress/badge/";
  var ENDPOINT_CANCEL = "/platform-runtime/workflow-progress/cancel/";
  var ENDPOINT_APPLY_FIX = "/platform-runtime/workflow-progress/apply-fix/";

  // Polling fallback cadence (ms) when EventSource unavailable.
  var POLL_INTERVAL_MS = 5000;
  var STREAM_RECONNECT_MS = 4000;
  // Render 502 HTML (~223 KB) during deploys — back off instead of hammering every 4–5s.
  var OUTAGE_BACKOFF_MS = 30000;

  function isPlatformOutageStatus(status) {
    return !status || status === 503 || (status >= 502 && status <= 504);
  }

  function scheduleStreamReconnect(delayMs) {
    var wait = typeof delayMs === "number" ? delayMs : STREAM_RECONNECT_MS;
    window.setTimeout(connectStream, wait);
  }

  function probeActiveBeforeReconnect() {
    return fetch(ENDPOINT_ACTIVE, { credentials: "same-origin" })
      .then(function (r) {
        if (r.status === 401 || r.status === 403) {
          return;
        }
        if (isPlatformOutageStatus(r.status)) {
          scheduleStreamReconnect(OUTAGE_BACKOFF_MS);
          return;
        }
        var ct = (r.headers.get("content-type") || "").toLowerCase();
        if (ct && ct.indexOf("json") === -1) {
          scheduleStreamReconnect(OUTAGE_BACKOFF_MS);
          return;
        }
        scheduleStreamReconnect(STREAM_RECONNECT_MS);
      })
      .catch(function () {
        scheduleStreamReconnect(OUTAGE_BACKOFF_MS);
      });
  }

  function pollActiveOnce() {
    return fetch(ENDPOINT_ACTIVE, { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok || isPlatformOutageStatus(r.status)) return null;
        var ct = (r.headers.get("content-type") || "").toLowerCase();
        if (ct.indexOf("json") === -1) return null;
        return r.json();
      })
      .then(function (data) {
        if (data) applySnapshot(data);
      })
      .catch(function () { /* next tick retries */ });
  }

  var state = {
    runs: [],
    open: false,
    eventSource: null,
    pollTimer: null,
    everyConnected: false,
    // Run ids we've already auto-popped the card for, so a still-active run
    // doesn't re-open the card after the user manually closes it on this page.
    autoShownRunIds: {},
  };

  // Statuses that mean the run is finished — a NEW run in one of these states
  // should NOT trigger the attention popup (nothing to watch).
  var TERMINAL_STATUSES = {
    completed: true,
    complete: true,
    succeeded: true,
    success: true,
    done: true,
    finished: true,
    cancelled: true,
    canceled: true,
  };

  function escapeHtml(value) {
    if (value === null || value === undefined) return "";
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getCsrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function buildChip() {
    var chip = document.createElement("button");
    chip.type = "button";
    chip.className = "rmc-wfp-chip";
    chip.id = "rmc-wfp-chip";
    chip.setAttribute("aria-label", "Workflow progress");
    chip.setAttribute("aria-haspopup", "dialog");
    chip.setAttribute("aria-expanded", "false");
    chip.setAttribute("aria-keyshortcuts", "g w, g f");
    chip.dataset.rmcWfpState = "idle";
    chip.innerHTML =
      '<i class="bi bi-hourglass-split rmc-wfp-chip__icon" aria-hidden="true"></i>' +
      '<span class="rmc-wfp-chip__count" hidden>0</span>';
    return chip;
  }

  function flightDeckPageUrl() {
    var el = document.getElementById("page-data-rmc-workflow-flight-deck");
    if (!el) return "/platform-runtime/workflow-progress/flight-deck/";
    try {
      var data = JSON.parse(el.textContent || "{}");
      return data.page_url || "/platform-runtime/workflow-progress/flight-deck/";
    } catch (_) {
      return "/platform-runtime/workflow-progress/flight-deck/";
    }
  }

  function buildCard() {
    var card = document.createElement("div");
    card.className = "rmc-wfp-card";
    card.id = "rmc-wfp-card";
    card.setAttribute("role", "dialog");
    card.setAttribute("aria-labelledby", "rmc-wfp-card-title");
    card.dataset.rmcWfpOpen = "false";
    card.innerHTML =
      '<div class="rmc-wfp-card__header">' +
      '<span class="rmc-wfp-card__title" id="rmc-wfp-card-title">' +
      '<i class="bi bi-hourglass-split" aria-hidden="true"></i> Workflow Progress' +
      "</span>" +
      '<div class="rmc-wfp-card__actions">' +
      '<a class="rmc-wfp-card__deck" href="' +
      escapeHtml(flightDeckPageUrl()) +
      '">Flight Deck</a>' +
      '<button type="button" class="rmc-wfp-card__explain" data-rmc-wfp-explain hidden>Explain</button>' +
      "</div>" +
      '<button type="button" class="rmc-wfp-card__close" aria-label="Close">' +
      '<i class="bi bi-x-lg" aria-hidden="true"></i>' +
      "</button>" +
      "</div>" +
      '<div class="rmc-wfp-card__body" id="rmc-wfp-card-body"></div>';
    return card;
  }

  function renderCard() {
    var body = document.getElementById("rmc-wfp-card-body");
    var explainBtn = document.querySelector("[data-rmc-wfp-explain]");
    if (explainBtn) explainBtn.hidden = !state.runs.length;
    if (!body) return;
    if (!state.runs.length) {
      body.innerHTML =
        '<div class="rmc-wfp-card__empty">' +
        '<i class="bi bi-check-circle" aria-hidden="true" style="font-size:1.5rem;display:block;margin-bottom:0.4rem;"></i>' +
        "No active workflows. The platform is idle." +
        "</div>";
      return;
    }
    var html = "";
    for (var i = 0; i < state.runs.length; i++) {
      html += renderRun(state.runs[i]);
    }
    body.innerHTML = html;
    wireRunActions(body);
  }

  function renderRun(run) {
    var status = run.status || "running";
    var pillClass = "rmc-wfp-run__pill--" + status;
    var label = escapeHtml(run.workflow_label || run.workflow_key || "Workflow");
    var current = escapeHtml(run.current_step_name || "starting…");
    var ordinal = run.current_step_ordinal || 0;
    var total = run.total_steps || 0;
    var ageSeconds = ageInSeconds(run.started_at);
    var ageText = ageSeconds < 60
      ? ageSeconds + "s"
      : Math.round(ageSeconds / 60) + "m" + (ageSeconds % 60 === 0 ? "" : " " + (ageSeconds % 60) + "s");
    var etaSeconds = Math.max(0, (run.expected_duration_seconds || 30) - ageSeconds);
    var etaText = etaSeconds === 0 ? "overdue" : "~" + etaSeconds + "s left";

    var pct = typeof run.progress_percent === "number" ? run.progress_percent : 0;
    if (!run.progress_percent && total && ordinal) {
      pct = Math.max(1, Math.min(99, Math.round(((ordinal - 0.35) / total) * 100)));
    }
    var bar = renderProgressBar(pct, status);
    var train = renderTrain(ordinal, total, status);
    var fix = run.suggested_remediation && Object.keys(run.suggested_remediation).length
      ? renderFix(run)
      : "";

    return (
      '<div class="rmc-wfp-run" data-rmc-wfp-state="' + escapeHtml(status) + '" data-run-id="' + escapeHtml(run.id) + '">' +
      '<div class="rmc-wfp-run__head">' +
      "<div>" +
      '<div class="rmc-wfp-run__title">' + label + "</div>" +
      '<div class="rmc-wfp-run__meta">' + (run.tenant_schema ? escapeHtml(run.tenant_schema) + " · " : "") + ageText + ' ago</div>' +
      "</div>" +
      '<span class="rmc-wfp-run__pill ' + pillClass + '">' + escapeHtml(status) + "</span>" +
      "</div>" +
      bar +
      '<div class="rmc-wfp-train">' + train + "</div>" +
      '<div class="rmc-wfp-run__step-row">' +
      "<span>Step " + ordinal + (total ? " / " + total : "") + ": <strong>" + current + "</strong></span>" +
      "<span>" + etaText + "</span>" +
      "</div>" +
      fix +
      "</div>"
    );
  }

  function progressStatusLabel(status) {
    if (status === "stuck") return "Needs attention";
    if (status === "failed") return "Failed";
    if (status === "degrading") return "Slowing";
    return "In progress";
  }

  function renderProgressBar(percent, status) {
    var safe = Math.max(0, Math.min(100, percent || 0));
    var state = status === "stuck" ? "stuck" : status === "failed" ? "failed" : "running";
    var label = progressStatusLabel(status);
    return (
      '<div class="rmc-wfp-bar" data-rmc-wfp-bar-state="' + escapeHtml(state) + '">' +
      '<div class="rmc-wfp-bar__label">' +
      '<span class="rmc-wfp-bar__status">' + escapeHtml(label) + "</span>" +
      '<span class="rmc-wfp-bar__pct" aria-hidden="true">' + safe + "%</span>" +
      "</div>" +
      '<div class="rmc-wfp-bar__track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + safe + '">' +
      '<div class="rmc-wfp-bar__fill" style="width:' + safe + '%;"></div>' +
      "</div>" +
      "</div>"
    );
  }

  function renderTrain(currentOrdinal, total, status) {
    if (!total || total < 1) {
      // No declared steps — show a single living bead.
      return '<span class="rmc-wfp-train__bead" data-status="' + escapeHtml(status === "stuck" ? "failed" : "running") + '"></span>';
    }
    var html = "";
    for (var i = 1; i <= total; i++) {
      var beadStatus;
      if (i < currentOrdinal) beadStatus = "done";
      else if (i === currentOrdinal) beadStatus = status === "stuck" ? "failed" : "running";
      else beadStatus = "pending";
      html += '<span class="rmc-wfp-train__bead" data-status="' + beadStatus + '"></span>';
      if (i < total) html += '<span class="rmc-wfp-train__rule"></span>';
    }
    return html;
  }

  function renderFix(run) {
    var rem = run.suggested_remediation || {};
    if (!rem.human_action) return "";
    var canApply = !!rem.auto_fix_available;
    return (
      '<div class="rmc-wfp-fix" data-run-id="' + escapeHtml(run.id) + '">' +
      '<div class="rmc-wfp-fix__title">AI suggested fix</div>' +
      '<div class="rmc-wfp-fix__body">' + escapeHtml(rem.human_action) + "</div>" +
      '<div class="rmc-wfp-fix__actions">' +
      (canApply
        ? '<button type="button" class="rmc-wfp-fix__btn rmc-wfp-fix__btn--ghost" data-rmc-wfp-action="preview-fix">Preview</button>' +
          '<button type="button" class="rmc-wfp-fix__btn" data-rmc-wfp-action="apply-fix">Apply</button>'
        : "") +
      '<button type="button" class="rmc-wfp-fix__btn rmc-wfp-fix__btn--ghost" data-rmc-wfp-action="cancel">Cancel run</button>' +
      "</div>" +
      "</div>"
    );
  }

  function ageInSeconds(startIso) {
    if (!startIso) return 0;
    try {
      var started = new Date(startIso).getTime();
      var now = Date.now();
      return Math.max(0, Math.floor((now - started) / 1000));
    } catch (_) {
      return 0;
    }
  }

  function wireRunActions(root) {
    var btns = root.querySelectorAll("[data-rmc-wfp-action]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].addEventListener("click", onRunAction);
    }
  }

  function onRunAction(evt) {
    var action = evt.currentTarget.getAttribute("data-rmc-wfp-action");
    var card = evt.currentTarget.closest("[data-run-id]");
    if (!card) return;
    var runId = card.getAttribute("data-run-id");
    if (!runId) return;
    var url = "";
    if (action === "apply-fix") url = ENDPOINT_APPLY_FIX + runId + "/";
    else if (action === "preview-fix") url = ENDPOINT_APPLY_FIX + runId + "/?dry_run=1";
    else if (action === "cancel") url = ENDPOINT_CANCEL + runId + "/";
    else return;
    fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        "Accept": "application/json",
      },
      credentials: "same-origin",
    })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        if (action === "preview-fix" && j) {
          var previewMsg = j.note || j.would_apply || JSON.stringify(j);
          if (window.alert) window.alert(String(previewMsg));
          return;
        }
        if (j && j.ok) {
          card.style.opacity = "0.5";
        }
        if (j && j.promotion && j.promotion.promote_autopilot) {
          var msg = j.promotion.message || "Enable autopilot for this fix kind?";
          if (window.confirm(msg)) {
            fetch("/platform-runtime/workflow-progress/autopilot/enable/", {
              method: "POST",
              headers: {
                "X-CSRFToken": getCsrfToken(),
                "Accept": "application/json",
                "Content-Type": "application/json",
              },
              credentials: "same-origin",
              body: JSON.stringify({
                workflow_key: j.promotion.workflow_key,
                auto_fix_kind: j.promotion.auto_fix_kind,
                promoted_from_successes: true,
              }),
            }).catch(function () {});
          }
        }
      })
      .catch(function () { /* network failures are surfaced on next tick */ });
  }

  function updateChip() {
    var chip = document.getElementById("rmc-wfp-chip");
    if (!chip) return;
    var stuck = 0;
    var degrading = 0;
    var running = 0;
    for (var i = 0; i < state.runs.length; i++) {
      if (state.runs[i].status === "stuck") stuck++;
      else if (state.runs[i].status === "degrading") degrading++;
      else if (state.runs[i].status === "running") running++;
    }
    var chipState;
    if (stuck > 0) chipState = "stuck";
    else if (degrading > 0) chipState = "degrading";
    else if (running > 0) chipState = "running";
    else chipState = "idle";
    chip.dataset.rmcWfpState = chipState;
    var countEl = chip.querySelector(".rmc-wfp-chip__count");
    if (countEl) {
      var total = stuck + degrading + running;
      if (total > 0) {
        countEl.textContent = String(total);
        countEl.hidden = false;
      } else {
        countEl.hidden = true;
      }
    }
  }

  function pickPrimaryRun() {
    if (!state.runs.length) return null;
    var primary = state.runs[0];
    for (var i = 0; i < state.runs.length; i++) {
      if (state.runs[i].status === "stuck") {
        return state.runs[i];
      }
      if (state.runs[i].status === "running") {
        primary = state.runs[i];
      }
    }
    return primary;
  }

  function buildInlineStripHtml(primary) {
    var pct = typeof primary.progress_percent === "number" ? primary.progress_percent : 0;
    var label = escapeHtml(primary.workflow_label || primary.workflow_key || "Workflow");
    var step = escapeHtml(primary.current_step_name || "starting…");
    return (
      '<div class="rmc-wfp-inline__inner">' +
      '<div class="rmc-wfp-inline__copy">' +
      '<strong class="rmc-wfp-inline__title">' + label + "</strong>" +
      '<span class="rmc-wfp-inline__step">' + step + "</span>" +
      "</div>" +
      renderProgressBar(pct, primary.status || "running") +
      '<button type="button" class="rmc-wfp-inline__open btn btn-sm btn-outline-secondary">' +
      "Details" +
      "</button>" +
      "</div>"
    );
  }

  function updateInlineStrip() {
    var strips = document.querySelectorAll("[data-rmc-wfp-inline]");
    if (!strips.length) return;
    var primary = pickPrimaryRun();
    if (!primary) {
      for (var h = 0; h < strips.length; h++) {
        strips[h].hidden = true;
        strips[h].innerHTML = "";
      }
      document.dispatchEvent(new CustomEvent("rmc-wfp-inline-updated"));
      return;
    }
    var html = buildInlineStripHtml(primary);
    for (var s = 0; s < strips.length; s++) {
      var strip = strips[s];
      strip.hidden = false;
      strip.innerHTML = html;
      var openBtn = strip.querySelector(".rmc-wfp-inline__open");
      if (openBtn) {
        openBtn.addEventListener("click", function (evt) {
          evt.preventDefault();
          if (!state.open) toggleCard();
        });
      }
    }
    document.dispatchEvent(new CustomEvent("rmc-wfp-inline-updated"));
  }

  function applySnapshot(payload) {
    if (!payload || !Array.isArray(payload.runs)) return;
    state.runs = payload.runs;
    // Auto-popup: when a workflow is freshly engaged, jump the progress card
    // open so the user always gets a live progress report without hunting for
    // the chip. Honors a manual close (we only re-open for a genuinely new run
    // id, tracked in state.autoShownRunIds), so it stays visible but never
    // becomes a fight. Disable per-deploy via the data flag if ever needed.
    var hasNewActiveRun = detectNewActiveRun(state.runs);
    updateChip();
    updateInlineStrip();
    if (hasNewActiveRun && !state.open && !autoPopupDisabled()) {
      setCardOpen(true);
    } else if (state.open) {
      renderCard();
    }
  }

  function autoPopupDisabled() {
    // Opt-out hook: <body data-rmc-wfp-autopopup="off"> or a global flag.
    if (window.__rmcWfpAutoPopupOff) return true;
    var body = document.body;
    return !!(body && body.getAttribute("data-rmc-wfp-autopopup") === "off");
  }

  function shouldConnectStream() {
    if (document.querySelector("[data-rmc-auth-landing]")) return false;
    if (document.querySelector("[data-rmc-wizard-shell]")) return false;
    try {
      if (window.SMS_OFFLINE_CONFIG && window.SMS_OFFLINE_CONFIG.sseStreamsEnabled === false) {
        return false;
      }
    } catch (_) {}
    return true;
  }

  function connectStream() {
    if (!shouldConnectStream()) {
      startPolling();
      return;
    }
    if (typeof EventSource === "undefined") {
      startPolling();
      return;
    }
    try {
      var es = new EventSource(ENDPOINT_STREAM, { withCredentials: true });
      state.eventSource = es;
      state.everyConnected = true;
      es.addEventListener("snapshot", function (ev) {
        try {
          applySnapshot(JSON.parse(ev.data));
        } catch (_) { /* malformed frame — ignore */ }
      });
      es.addEventListener("busy", function () {
        es.close();
        state.eventSource = null;
        scheduleStreamReconnect(OUTAGE_BACKOFF_MS);
      });
      es.addEventListener("bye", function () {
        // Server-side graceful close; reconnect after a small jitter.
        es.close();
        state.eventSource = null;
        setTimeout(connectStream, 800 + Math.floor(Math.random() * 800));
      });
      es.onerror = function () {
        es.close();
        state.eventSource = null;
        probeActiveBeforeReconnect();
      };
    } catch (_) {
      startPolling();
    }
  }

  function startPolling() {
    if (state.pollTimer) return;
    state.pollTimer = window.setInterval(pollActiveOnce, POLL_INTERVAL_MS);
    pollActiveOnce();
  }

  function setCardOpen(open) {
    state.open = !!open;
    var chip = document.getElementById("rmc-wfp-chip");
    var card = document.getElementById("rmc-wfp-card");
    if (!chip || !card) return;
    chip.setAttribute("aria-expanded", state.open ? "true" : "false");
    card.dataset.rmcWfpOpen = state.open ? "true" : "false";
    if (state.open) renderCard();
  }

  function toggleCard() {
    setCardOpen(!state.open);
  }

  // Returns true when the snapshot carries an ACTIVE run we have not yet popped
  // the card for — the trigger for the auto-attention behavior. Marks every
  // current run id as seen so the same run won't re-pop after a manual close.
  function detectNewActiveRun(runs) {
    var foundNew = false;
    for (var i = 0; i < runs.length; i++) {
      var run = runs[i];
      if (!run || !run.id) continue;
      var status = String(run.status || "running").toLowerCase();
      var alreadyShown = !!state.autoShownRunIds[run.id];
      state.autoShownRunIds[run.id] = true;
      if (!alreadyShown && !TERMINAL_STATUSES[status]) {
        foundNew = true;
      }
    }
    return foundNew;
  }

  function onKeydown(evt) {
    // g w shortcut.
    if (evt.target && (evt.target.tagName === "INPUT" || evt.target.tagName === "TEXTAREA" || evt.target.isContentEditable)) {
      return;
    }
    if (evt.key === "g" && !evt.repeat) {
      window.__rmcWfpGPending = Date.now();
      window.setTimeout(function () { window.__rmcWfpGPending = 0; }, 1000);
      return;
    }
    if (evt.key === "w" && window.__rmcWfpGPending && (Date.now() - window.__rmcWfpGPending) < 1000) {
      window.__rmcWfpGPending = 0;
      toggleCard();
    }
    if (evt.key === "f" && window.__rmcWfpGPending && (Date.now() - window.__rmcWfpGPending) < 1000) {
      window.__rmcWfpGPending = 0;
      window.location.href = flightDeckPageUrl();
    }
    if (evt.key === "Escape" && state.open) {
      toggleCard();
    }
  }

  function adoptRegisteredSlotChip() {
    // The assist-dock registry paints a `workflow-progress` slot chip with a
    // visible "Workflow" label but binds no click handler (only the `voice`
    // slot gets one in `rmc-assist-dock.js::buildRegistryChip`). When that
    // chip is present we adopt it: tag it with the id this module's handlers
    // look up, mirror the count badge contract, and skip minting a duplicate
    // floating chip. Returns the adopted node or null.
    var slotChip = document.querySelector('[data-rmc-assist-slot-id="workflow-progress"]');
    if (!slotChip) return null;
    slotChip.id = "rmc-wfp-chip";
    slotChip.classList.add("rmc-wfp-chip");
    slotChip.setAttribute("aria-haspopup", "dialog");
    slotChip.setAttribute("aria-expanded", "false");
    slotChip.dataset.rmcWfpState = "idle";
    if (!slotChip.querySelector(".rmc-wfp-chip__count")) {
      var count = document.createElement("span");
      count.className = "rmc-wfp-chip__count";
      count.hidden = true;
      count.textContent = "0";
      slotChip.appendChild(count);
    }
    return slotChip;
  }

  function mountChipTarget() {
    return document.querySelector("[data-rmc-wfp-tray-slot]");
  }

  function attachChip(chip) {
    if (!chip) return;
    chip.addEventListener("click", toggleCard);
  }

  function placeChip(chip, adopted) {
    var traySlot = mountChipTarget();
    if (traySlot) {
      traySlot.appendChild(chip);
      attachChip(chip);
      return;
    }
    if (adopted) {
      attachChip(adopted);
      return;
    }
    // Park the chip into the assist-dock host if it exists; otherwise float bottom-right.
    var dock = document.querySelector(
      '[data-rmc-assist-dock-host],[data-rmc-assist-dock="mounted"]'
    );
    if (dock) {
      dock.appendChild(chip);
    } else {
      chip.style.position = "fixed";
      chip.style.right = "1rem";
      chip.style.bottom = "calc(env(safe-area-inset-bottom, 0px) + 5.5rem)";
      chip.style.zIndex = "10465";
      document.body.appendChild(chip);
    }
    attachChip(chip);
    // The dock may finish painting AFTER us; if its labeled `workflow-progress`
    // slot chip appears later, re-adopt it and drop the floating duplicate.
    document.addEventListener("rmc-assist-dock-mounted", function onDockReady() {
      document.removeEventListener("rmc-assist-dock-mounted", onDockReady);
      var slot = document.querySelector('[data-rmc-assist-slot-id="workflow-progress"]');
      if (!slot || slot.id === "rmc-wfp-chip") return;
      chip.removeEventListener("click", toggleCard);
      if (chip.parentNode) chip.parentNode.removeChild(chip);
      var late = adoptRegisteredSlotChip();
      if (late) {
        placeChip(late, true);
        updateChip();
      }
    });
  }

  function mount() {
    if (!shouldConnectStream()) return;
    if (document.getElementById("rmc-wfp-chip")) return;
    var card = buildCard();
    document.body.appendChild(card);

    var adopted = adoptRegisteredSlotChip();
    var chip = adopted || buildChip();

    placeChip(chip, adopted);

    document.addEventListener("rmc-operator-tools-ready", function onToolsReady() {
      document.removeEventListener("rmc-operator-tools-ready", onToolsReady);
      var existing = document.getElementById("rmc-wfp-chip");
      var traySlot = mountChipTarget();
      if (!existing || !traySlot || traySlot.contains(existing)) return;
      traySlot.appendChild(existing);
    });

    var closeBtn = card.querySelector(".rmc-wfp-card__close");
    if (closeBtn) closeBtn.addEventListener("click", toggleCard);
    var explainBtn = card.querySelector("[data-rmc-wfp-explain]");
    if (explainBtn) {
      explainBtn.addEventListener("click", function () {
        window.__rmcWorkflowCopilotContext = {
          active_run_ids: state.runs.map(function (r) { return r.id; }),
          runs: state.runs.slice(0, 5),
        };
        document.dispatchEvent(
          new CustomEvent("rmc-workflow-copilot-context", {
            detail: window.__rmcWorkflowCopilotContext,
          })
        );
        var trigger = document.getElementById("aiCopilotTrigger");
        if (trigger) trigger.click();
      });
    }
    document.addEventListener("keydown", onKeydown);

    connectStream();

    if (window.RMCAssistDock && window.RMCAssistDock.syncAssistRailMetrics) {
      window.RMCAssistDock.syncAssistRailMetrics();
    }
  }

  document.addEventListener("rmc-assist-dock-mounted", function () {
    if (window.RMCAssistDock && window.RMCAssistDock.syncAssistRailMetrics) {
      window.requestAnimationFrame(function () {
        window.RMCAssistDock.syncAssistRailMetrics();
      });
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
