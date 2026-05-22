/* ============================================================
   rmc-copilot-rail.js — v3.58 (2026-05-22)
   ------------------------------------------------------------
   AI Copilot rail + Operator Notebook UX wiring.

   Responsibilities:
     1. Copilot rail expand/collapse via [data-rmc-copilot-toggle].
        Cmd/Ctrl+K shifts focus to the textarea inside the rail
        (auto-expands if collapsed).
     2. Copilot tab routing: collapsed-rail icons with
        [data-rmc-copilot-tab="actions|threads|notebook"] expand the
        rail AND set [data-active-tab] on the rail so different sections
        come forward.
     3. Suggestion click → autofill the rail input + place caret at end.
        (Send wiring stays server-routed; see services/ai_helpers.py.)
     4. Operator notebook:
        - Minimize/restore via the head ─ button or the ✎ copilot icon.
        - Drag from the head: persists position per-operator in
          localStorage. Snap-to-corner on release within 80px of an edge.
        - Recent notes: capture on submit, keep last N (10) in
          localStorage, render compact list inside the widget.
          Click a recent entry to copy its body back into the field.

   Idempotent — runs once per page even if the script is loaded twice.
   No external dependencies. CSP-safe (no inline handlers, all listeners
   attached via addEventListener).
   ============================================================ */
(function () {
  "use strict";

  if (typeof document === "undefined") { return; }
  if (document.documentElement.dataset.rmcCopilotInited === "1") { return; }
  document.documentElement.dataset.rmcCopilotInited = "1";

  /* === Shell helpers ========================================== */
  function findShell(el) {
    while (el && el !== document.body) {
      if (el.classList && el.classList.contains("rmc-app-shell")) {
        return el;
      }
      el = el.parentElement;
    }
    return document.querySelector(".rmc-app-shell");
  }

  function setShellState(shell, state) {
    if (!shell) { return; }
    shell.setAttribute("data-copilot", state);
  }

  function toggleShell(shell) {
    if (!shell) { return; }
    var current = shell.getAttribute("data-copilot") || "collapsed";
    setShellState(shell, current === "expanded" ? "collapsed" : "expanded");
  }

  function findRail() {
    return document.querySelector("[data-rmc-copilot-rail]");
  }

  function focusRailInput(shell) {
    if (!shell) { return; }
    setShellState(shell, "expanded");
    var input = shell.querySelector("[data-rmc-copilot-input]");
    if (input && typeof input.focus === "function") {
      window.setTimeout(function () { input.focus(); }, 0);
    }
  }

  function setRailActiveTab(tab) {
    var rail = findRail();
    if (!rail) { return; }
    rail.setAttribute("data-rmc-copilot-active-tab", tab);
  }

  /* === Notebook helpers ======================================= */
  var NOTEBOOK_POS_KEY = "rmc-operator-notebook-position";
  var NOTEBOOK_NOTES_KEY = "rmc-operator-notebook-recent";
  var NOTEBOOK_HISTORY_OPEN_KEY = "rmc-operator-notebook-history-open";
  var NOTEBOOK_DEFAULT_LIMIT = 10;

  function findNotebook() {
    return document.querySelector("[data-rmc-operator-notebook]");
  }

  function toggleNotebookMinimized() {
    var nb = findNotebook();
    if (!nb) { return; }
    var current = nb.getAttribute("data-rmc-notebook-state") || "open";
    nb.setAttribute("data-rmc-notebook-state", current === "minimized" ? "open" : "minimized");
  }

  /* --- Drag with snap-to-corner --------------------------------- */
  function readSavedNotebookPosition() {
    try {
      var raw = window.localStorage.getItem(NOTEBOOK_POS_KEY);
      if (!raw) { return null; }
      var parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" &&
          typeof parsed.corner === "string") {
        return parsed;
      }
    } catch (_e) {}
    return null;
  }

  function writeSavedNotebookPosition(pos) {
    try { window.localStorage.setItem(NOTEBOOK_POS_KEY, JSON.stringify(pos)); }
    catch (_e) {}
  }

  function applyCorner(nb, corner) {
    if (!nb) { return; }
    /* Reset all four corner anchors, then set the two for this corner. */
    nb.style.left = "auto";
    nb.style.right = "auto";
    nb.style.top = "auto";
    nb.style.bottom = "auto";
    /* Operator-set fixed insets (mirror the v3.55.0 CSS defaults of
       bottom: 100px + right: 80px when "bottom-right"). */
    if (corner.indexOf("top") === 0) {
      nb.style.top = "92px";
    } else {
      nb.style.bottom = "100px";
    }
    if (corner.indexOf("-right") > -1) {
      nb.style.right = "80px";
    } else {
      nb.style.left = "80px";
    }
    nb.setAttribute("data-rmc-notebook-corner", corner);
  }

  function applyFreePosition(nb, leftPx, topPx) {
    if (!nb) { return; }
    nb.style.right = "auto";
    nb.style.bottom = "auto";
    nb.style.left = leftPx + "px";
    nb.style.top = topPx + "px";
    nb.removeAttribute("data-rmc-notebook-corner");
  }

  function nearestCorner(nb) {
    var rect = nb.getBoundingClientRect();
    var w = window.innerWidth;
    var h = window.innerHeight;
    var cx = rect.left + rect.width / 2;
    var cy = rect.top + rect.height / 2;
    var v = cy < h / 2 ? "top" : "bottom";
    var hor = cx < w / 2 ? "left" : "right";
    return v + "-" + hor;
  }

  function distanceToEdge(nb) {
    var rect = nb.getBoundingClientRect();
    var w = window.innerWidth;
    var h = window.innerHeight;
    return Math.min(rect.left, rect.top, w - rect.right, h - rect.bottom);
  }

  function restoreNotebookPosition() {
    var nb = findNotebook();
    if (!nb) { return; }
    var saved = readSavedNotebookPosition();
    if (!saved) { return; }
    if (saved.corner && saved.corner !== "free") {
      applyCorner(nb, saved.corner);
      return;
    }
    if (typeof saved.left === "number" && typeof saved.top === "number") {
      applyFreePosition(nb, saved.left, saved.top);
    }
  }

  function wireNotebookDrag() {
    var nb = findNotebook();
    if (!nb) { return; }
    if (nb.getAttribute("data-rmc-notebook-draggable") !== "1") { return; }
    var handle = nb.querySelector("[data-rmc-notebook-drag-handle]");
    if (!handle) { return; }

    var dragging = false;
    var startX = 0, startY = 0;
    var origLeft = 0, origTop = 0;

    function onPointerDown(ev) {
      /* Ignore drags that originate from action buttons inside the head — they
         have their own click handlers. */
      if (ev.target && typeof ev.target.closest === "function") {
        if (ev.target.closest("button")) { return; }
      }
      dragging = true;
      var rect = nb.getBoundingClientRect();
      origLeft = rect.left;
      origTop = rect.top;
      startX = ev.clientX;
      startY = ev.clientY;
      applyFreePosition(nb, origLeft, origTop);
      nb.setAttribute("data-rmc-notebook-dragging", "1");
      if (handle.setPointerCapture) {
        try { handle.setPointerCapture(ev.pointerId); } catch (_e) {}
      }
      ev.preventDefault();
    }

    function onPointerMove(ev) {
      if (!dragging) { return; }
      var dx = ev.clientX - startX;
      var dy = ev.clientY - startY;
      var newLeft = origLeft + dx;
      var newTop = origTop + dy;
      /* Clamp inside viewport with a 12px margin. */
      var rect = nb.getBoundingClientRect();
      var maxLeft = window.innerWidth - rect.width - 12;
      var maxTop = window.innerHeight - rect.height - 12;
      newLeft = Math.max(12, Math.min(maxLeft, newLeft));
      newTop = Math.max(12, Math.min(maxTop, newTop));
      applyFreePosition(nb, newLeft, newTop);
    }

    function onPointerUp(ev) {
      if (!dragging) { return; }
      dragging = false;
      nb.removeAttribute("data-rmc-notebook-dragging");
      /* Snap to nearest corner when within 80px of an edge. */
      var snap = distanceToEdge(nb) <= 80;
      if (snap) {
        var corner = nearestCorner(nb);
        applyCorner(nb, corner);
        writeSavedNotebookPosition({ corner: corner });
      } else {
        var rect = nb.getBoundingClientRect();
        writeSavedNotebookPosition({
          corner: "free",
          left: Math.round(rect.left),
          top: Math.round(rect.top)
        });
      }
      ev.preventDefault();
    }

    if (window.PointerEvent) {
      handle.addEventListener("pointerdown", onPointerDown, false);
      window.addEventListener("pointermove", onPointerMove, false);
      window.addEventListener("pointerup", onPointerUp, false);
      window.addEventListener("pointercancel", onPointerUp, false);
    } else {
      /* Mouse-only fallback. */
      handle.addEventListener("mousedown", function (ev) {
        ev.clientX = ev.clientX; ev.clientY = ev.clientY;
        onPointerDown(ev);
      }, false);
      window.addEventListener("mousemove", onPointerMove, false);
      window.addEventListener("mouseup", onPointerUp, false);
    }
  }

  /* --- Recent notes -------------------------------------------- */
  function readRecentNotes() {
    try {
      var raw = window.localStorage.getItem(NOTEBOOK_NOTES_KEY);
      if (!raw) { return []; }
      var parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) { return parsed; }
    } catch (_e) {}
    return [];
  }

  function writeRecentNotes(notes) {
    try { window.localStorage.setItem(NOTEBOOK_NOTES_KEY, JSON.stringify(notes)); }
    catch (_e) {}
  }

  function recordNote(body) {
    var nb = findNotebook();
    if (!nb) { return; }
    var limit = parseInt(nb.getAttribute("data-rmc-notebook-recent-limit") || "", 10);
    if (!limit || limit < 1) { limit = NOTEBOOK_DEFAULT_LIMIT; }
    var trimmed = (body || "").trim();
    if (!trimmed) { return; }
    var notes = readRecentNotes();
    /* Newest first. */
    notes.unshift({ body: trimmed, ts: Date.now() });
    if (notes.length > limit) { notes = notes.slice(0, limit); }
    writeRecentNotes(notes);
    renderRecentNotes();
  }

  function formatRelativeTime(ts) {
    var seconds = Math.floor((Date.now() - ts) / 1000);
    if (seconds < 60) { return seconds + "s"; }
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) { return minutes + "m"; }
    var hours = Math.floor(minutes / 60);
    if (hours < 24) { return hours + "h"; }
    var days = Math.floor(hours / 24);
    if (days < 7) { return days + "d"; }
    var d = new Date(ts);
    var m = d.getMonth() + 1;
    var dd = d.getDate();
    return m + "/" + dd;
  }

  function clipPreview(body) {
    var s = (body || "").replace(/\s+/g, " ").trim();
    if (s.length <= 70) { return s; }
    return s.slice(0, 70) + "…";
  }

  function renderRecentNotes() {
    var list = document.querySelector("[data-rmc-notebook-history-list]");
    if (!list) { return; }
    var notes = readRecentNotes();
    list.innerHTML = "";
    var count = notes.length;
    var countEl = document.querySelector("[data-rmc-notebook-history-count]");
    if (countEl) { countEl.textContent = String(count); }
    var emptyEl = document.querySelector("[data-rmc-notebook-history-empty]");
    if (emptyEl) { emptyEl.style.display = count === 0 ? "" : "none"; }
    for (var i = 0; i < notes.length; i++) {
      var n = notes[i];
      if (!n || typeof n.body !== "string") { continue; }
      var li = document.createElement("li");
      li.className = "lx-notebook__history-item";
      li.setAttribute("data-rmc-notebook-history-index", String(i));
      var preview = document.createElement("span");
      preview.className = "lx-notebook__history-preview";
      preview.textContent = clipPreview(n.body);
      var age = document.createElement("span");
      age.className = "lx-notebook__history-age";
      age.textContent = formatRelativeTime(n.ts || Date.now());
      li.appendChild(preview);
      li.appendChild(age);
      list.appendChild(li);
    }
  }

  function applyHistoryStateFromStorage() {
    var nb = findNotebook();
    if (!nb) { return; }
    var hist = nb.querySelector("[data-rmc-notebook-history]");
    if (!hist) { return; }
    var open = false;
    try { open = window.localStorage.getItem(NOTEBOOK_HISTORY_OPEN_KEY) === "1"; }
    catch (_e) {}
    hist.setAttribute("data-rmc-notebook-history-state", open ? "open" : "collapsed");
  }

  function toggleHistory() {
    var nb = findNotebook();
    if (!nb) { return; }
    var hist = nb.querySelector("[data-rmc-notebook-history]");
    if (!hist) { return; }
    var open = hist.getAttribute("data-rmc-notebook-history-state") === "open";
    var next = open ? "collapsed" : "open";
    hist.setAttribute("data-rmc-notebook-history-state", next);
    try { window.localStorage.setItem(NOTEBOOK_HISTORY_OPEN_KEY, next === "open" ? "1" : "0"); }
    catch (_e) {}
  }

  function copyEntryToField(index) {
    var notes = readRecentNotes();
    if (index < 0 || index >= notes.length) { return; }
    var note = notes[index];
    if (!note) { return; }
    var field = document.querySelector("[data-rmc-notebook-field]");
    if (!field) { return; }
    field.value = note.body || "";
    field.focus();
    /* Place caret at end. */
    try {
      var len = field.value.length;
      field.setSelectionRange(len, len);
    } catch (_e) {}
  }

  function wireNotebookForm() {
    var nb = findNotebook();
    if (!nb) { return; }
    var form = nb.querySelector("[data-rmc-notebook-form]");
    if (!form) { return; }
    form.addEventListener("submit", function (_ev) {
      /* Capture-on-submit (not on response) so local history is up-to-date
         even when save_url is empty (purely local) or returns an error. */
      var field = form.querySelector("[data-rmc-notebook-field]");
      var value = field ? field.value : "";
      recordNote(value);
      /* If no save_url is configured, suppress the form post entirely so
         the browser does not navigate to a 404 / about:blank. */
      var action = (form.getAttribute("action") || "").trim();
      if (!action) {
        _ev.preventDefault();
        if (field) { field.value = ""; }
      }
      /* When action IS set, let the form post normally — server records
         the entry server-side as well. */
    }, false);
  }

  /* === Send button → POST /studio/copilot/rail/send/ =============== */
  /* v3.58.5 — Prefer SSE streaming endpoint when fetch+ReadableStream is
     available so the operator sees progressive ink; legacy JSON endpoint
     stays as the fallback. */
  var SEND_ENDPOINT = "/studio/copilot/rail/send/";
  var SEND_STREAM_ENDPOINT = "/studio/copilot/rail/send-stream/";
  var SUPPORTS_FETCH_STREAM = (function () {
    try {
      return typeof ReadableStream === "function"
        && typeof TextDecoder === "function"
        && typeof fetch === "function";
    } catch (_e) { return false; }
  })();
  var sending = false;

  function getCSRFToken() {
    var name = "csrftoken=";
    var cookies = (document.cookie || "").split(";");
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name) === 0) {
        return decodeURIComponent(c.substring(name.length));
      }
    }
    return "";
  }

  function appendThreadMessage(role, text) {
    var thread = document.querySelector(".lx-copilot__thread");
    if (!thread) { return; }
    var div = document.createElement("div");
    div.className = "lx-copilot__msg lx-copilot__msg--" + (role === "user" ? "user" : "ai");
    div.textContent = text || "";
    /* Insert above the suggestions block so the latest reply is read
       next to the prompt, not below the historical chips. */
    var suggestions = thread.querySelector(".lx-copilot__suggestions");
    if (suggestions) {
      thread.insertBefore(div, suggestions);
    } else {
      thread.appendChild(div);
    }
  }

  function updatePostureFromSendReply(source) {
    var pill = document.querySelector("[data-rmc-copilot-rail-posture]");
    if (!pill) { return; }
    if (source === "local") { pill.setAttribute("data-state", "live_local"); }
    else if (source === "cloud") { pill.setAttribute("data-state", "live_cloud"); }
    else if (source === "rules") { pill.setAttribute("data-state", "guided"); }
    else if (source === "unavailable") { pill.setAttribute("data-state", "unavailable"); }
    var label = pill.querySelector("[data-rmc-copilot-rail-posture-label]");
    if (label) {
      if (source === "local") { label.textContent = "Live · local AI"; }
      else if (source === "cloud") { label.textContent = "Live · cloud AI"; }
      else if (source === "rules") { label.textContent = "Guided mode"; }
      else if (source === "unavailable") { label.textContent = "AI unavailable"; }
    }
  }

  /* Append a placeholder AI message element and return it so streaming
     deltas can be concatenated into one bubble instead of one-per-frame. */
  function appendStreamingAIBubble() {
    var thread = document.querySelector(".lx-copilot__thread");
    if (!thread) { return null; }
    var div = document.createElement("div");
    div.className = "lx-copilot__msg lx-copilot__msg--ai lx-copilot__msg--streaming";
    div.setAttribute("aria-live", "polite");
    div.textContent = "";
    var suggestions = thread.querySelector(".lx-copilot__suggestions");
    if (suggestions) { thread.insertBefore(div, suggestions); }
    else { thread.appendChild(div); }
    return div;
  }

  /* Parse an SSE buffer slice and return { events, remainder }.
     Frames are separated by a blank line per spec. */
  function parseSSEChunk(remainder, chunk) {
    var buf = remainder + chunk;
    var events = [];
    var idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      var raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      var lines = raw.split("\n");
      var name = "message";
      var data = "";
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        if (line.indexOf("event:") === 0) { name = line.slice(6).trim(); }
        else if (line.indexOf("data:") === 0) {
          if (data) { data += "\n"; }
          data += line.slice(5).replace(/^ /, "");
        }
      }
      events.push({ name: name, data: data });
    }
    return { events: events, remainder: buf };
  }

  function sendCopilotMessageStreaming(text, mode, sendBtn) {
    var bubble = appendStreamingAIBubble();
    var assembled = "";
    var remainder = "";
    var sawDone = false;

    return fetch(SEND_STREAM_ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
      },
      body: JSON.stringify({ message: text, mode: mode }),
    }).then(function (r) {
      if (!r.body || !r.body.getReader) { throw new Error("stream-unsupported"); }
      var reader = r.body.getReader();
      var decoder = new TextDecoder("utf-8");

      function pump() {
        return reader.read().then(function (step) {
          if (step.done) {
            /* Stream ended without a "done" frame — treat as best-effort. */
            if (!sawDone && bubble && !assembled) {
              bubble.textContent = "(no reply)";
            }
            return;
          }
          var parsed = parseSSEChunk(remainder, decoder.decode(step.value, { stream: true }));
          remainder = parsed.remainder;
          for (var i = 0; i < parsed.events.length; i++) {
            var ev = parsed.events[i];
            var payload = null;
            try { payload = JSON.parse(ev.data); } catch (_e) { payload = null; }
            if (!payload) { continue; }
            if (ev.name === "delta" && typeof payload.text === "string" && bubble) {
              assembled += payload.text;
              bubble.textContent = assembled;
            } else if (ev.name === "ready" && payload.posture_mode) {
              /* Could flash a "thinking" state here; intentionally quiet. */
            } else if (ev.name === "done") {
              sawDone = true;
              if (bubble) {
                /* Prefer the server's canonical reply text in case any chunks
                   were dropped by an intermediary. */
                if (payload.reply) { bubble.textContent = payload.reply; }
                bubble.classList.remove("lx-copilot__msg--streaming");
              }
              if (payload.source) { updatePostureFromSendReply(payload.source); }
            } else if (ev.name === "error") {
              if (bubble) { bubble.textContent = "The assistant returned an error."; }
              updatePostureFromSendReply("unavailable");
            }
          }
          return pump();
        });
      }

      return pump();
    });
  }

  function sendCopilotMessageJSON(text, mode) {
    return fetch(SEND_ENDPOINT, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
      },
      body: JSON.stringify({ message: text, mode: mode }),
    }).then(function (r) {
      return r.json().catch(function () { return null; });
    }).then(function (data) {
      if (!data) {
        appendThreadMessage("ai", "AI is unavailable right now.");
        updatePostureFromSendReply("unavailable");
        return;
      }
      if (data.reply) { appendThreadMessage("ai", data.reply); }
      if (data.source) { updatePostureFromSendReply(data.source); }
    });
  }

  function sendCopilotMessage() {
    if (sending) { return; }
    var input = document.querySelector("[data-rmc-copilot-input]");
    if (!input) { return; }
    var text = (input.value || "").trim();
    if (!text) { return; }

    sending = true;
    var sendBtn = document.querySelector(".lx-copilot__send");
    if (sendBtn) { sendBtn.disabled = true; sendBtn.setAttribute("aria-busy", "true"); }

    appendThreadMessage("user", text);
    input.value = "";

    var mode = "operator";
    var rail = findRail();
    if (rail) {
      var tab = rail.getAttribute("data-rmc-copilot-active-tab");
      if (tab) { mode = tab; }
    }

    var pipeline;
    if (SUPPORTS_FETCH_STREAM) {
      pipeline = sendCopilotMessageStreaming(text, mode, sendBtn)
        .catch(function () {
          /* Streaming fell through (likely unsupported transport on this
             deployment) — fall back to the legacy JSON endpoint so the
             operator still gets a reply. */
          return sendCopilotMessageJSON(text, mode);
        });
    } else {
      pipeline = sendCopilotMessageJSON(text, mode);
    }

    pipeline.catch(function () {
      appendThreadMessage("ai", "Couldn't reach the assistant. Check your connection and try again.");
      updatePostureFromSendReply("unavailable");
    }).then(function () {
      sending = false;
      if (sendBtn) { sendBtn.disabled = false; sendBtn.removeAttribute("aria-busy"); }
    });
  }

  /* === Click delegation ======================================== */
  function onClick(ev) {
    var target = ev.target;
    if (!target || typeof target.closest !== "function") { return; }

    /* Notebook history toggle (the ⋯ button). */
    if (target.closest("[data-rmc-notebook-history-toggle]")) {
      ev.preventDefault();
      toggleHistory();
      return;
    }

    /* Notebook recent-entry click → copy back to field. */
    var historyItem = target.closest("[data-rmc-notebook-history-index]");
    if (historyItem) {
      ev.preventDefault();
      var idx = parseInt(historyItem.getAttribute("data-rmc-notebook-history-index") || "-1", 10);
      copyEntryToField(idx);
      return;
    }

    /* Notebook minimize (─) or copilot pencil-icon (✎) — both toggle the
       notebook minimized/open state. */
    var nbMinBtn = target.closest(".lx-notebook__min");
    var nbToggleBtn = target.closest("[data-rmc-operator-notebook-toggle]");
    if (nbMinBtn || nbToggleBtn) {
      ev.preventDefault();
      toggleNotebookMinimized();
      return;
    }

    /* Copilot rail tab routing — collapsed icons set the active tab
       AND expand the rail. */
    var tabBtn = target.closest("[data-rmc-copilot-tab]");
    if (tabBtn) {
      ev.preventDefault();
      var tab = tabBtn.getAttribute("data-rmc-copilot-tab") || "chat";
      setRailActiveTab(tab);
      setShellState(findShell(tabBtn), "expanded");
      return;
    }

    /* Copilot suggestion click → autofill the input. */
    var sug = target.closest("[data-rmc-copilot-suggestion]");
    if (sug) {
      ev.preventDefault();
      var input = document.querySelector("[data-rmc-copilot-input]");
      if (input) {
        input.value = sug.textContent.trim();
        input.focus();
        try {
          var len = input.value.length;
          input.setSelectionRange(len, len);
        } catch (_e) {}
      }
      return;
    }

    /* Copilot Send button click → POST through ai_helpers gateway. */
    var send = target.closest(".lx-copilot__send");
    if (send) {
      ev.preventDefault();
      sendCopilotMessage();
      return;
    }

    /* Plain expand/collapse toggle. */
    var toggle = target.closest("[data-rmc-copilot-toggle]");
    if (!toggle) { return; }
    ev.preventDefault();
    toggleShell(findShell(toggle));
  }

  /* Enter (without Shift) in the rail input submits; Shift+Enter inserts newline. */
  function onRailInputKeydown(ev) {
    var target = ev.target;
    if (!target || !target.matches || !target.matches("[data-rmc-copilot-input]")) { return; }
    var key = ev.key || "";
    if (key === "Enter" && !ev.shiftKey && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
      ev.preventDefault();
      sendCopilotMessage();
    }
  }

  function onKeydown(ev) {
    var key = (ev.key || "").toLowerCase();
    if (key !== "k") { return; }
    if (!(ev.metaKey || ev.ctrlKey)) { return; }
    if (ev.altKey || ev.shiftKey) { return; }
    var rail = findRail();
    if (!rail) { return; }
    ev.preventDefault();
    focusRailInput(findShell(rail));
  }

  /* === Boot ==================================================== */
  function boot() {
    restoreNotebookPosition();
    applyHistoryStateFromStorage();
    renderRecentNotes();
    wireNotebookDrag();
    wireNotebookForm();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, false);
  } else {
    boot();
  }

  document.addEventListener("click", onClick, false);
  document.addEventListener("keydown", onKeydown, false);
  document.addEventListener("keydown", onRailInputKeydown, false);
})();
