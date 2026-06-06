/**
 * List bulk-select grammar — checkbox column, sticky action bar, copilot/lens hooks, POST mutations.
 */
(function () {
  "use strict";

  var confirmDialog = null;
  var pendingPost = null;

  function parseActions(table) {
    var raw = table.getAttribute("data-rmc-bulk-actions");
    if (!raw) { return []; }
    try {
      var parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (_e) {
      return [];
    }
  }

  function getBar(table) {
    var id = table.getAttribute("data-rmc-bulk-bar-id");
    if (id) {
      var byId = document.querySelector('[data-rmc-list-bulk-bar][data-rmc-bulk-bar-for="' + id + '"]');
      if (byId) { return byId; }
    }
    var prev = table.previousElementSibling;
    if (prev && prev.matches("[data-rmc-list-bulk-bar]")) { return prev; }
    var scope =
      table.closest(
        "[data-rmc-page-archetype], [data-page-archetype], .container-fluid, main, #cp-main-content"
      ) || document.body;
    return scope.querySelector("[data-rmc-list-bulk-bar]");
  }

  function selectedRows(table) {
    return Array.prototype.slice.call(
      table.querySelectorAll("tbody [data-rmc-bulk-row]:checked")
    );
  }

  function rowPayload(input) {
    var tr = input.closest("tr");
    return {
      value: input.value || "",
      label: input.getAttribute("data-rmc-bulk-label") || tr.getAttribute("data-rmc-row-title") || "",
      slug: input.getAttribute("data-rmc-bulk-slug") || "",
      href: tr.getAttribute("data-rmc-bulk-href") || "",
      row: tr,
    };
  }

  function readCookie(name) {
    var match = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "=([^;]*)")
    );
    return match ? decodeURIComponent(match[1]) : "";
  }

  function csrfToken() {
    var input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input && input.value) { return input.value; }
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content && meta.content !== "NOTPROVIDED") { return meta.content; }
    return readCookie("csrftoken") || readCookie("rmc_manager_csrftoken") || "";
  }

  function ensureConfirmDialog() {
    if (confirmDialog) { return confirmDialog; }
    confirmDialog = document.querySelector("[data-rmc-bulk-confirm-dialog]");
    if (!confirmDialog) { return null; }
    var form = confirmDialog.querySelector("form");
    var phraseInput = confirmDialog.querySelector("[data-rmc-bulk-confirm-phrase-input]");
    var submitBtn = confirmDialog.querySelector("[data-rmc-bulk-confirm-submit]");
    var cancelBtn = confirmDialog.querySelector("[data-rmc-bulk-confirm-cancel]");
    var errorEl = confirmDialog.querySelector("[data-rmc-bulk-confirm-error]");

    if (cancelBtn) {
      cancelBtn.addEventListener("click", function () {
        confirmDialog.close("cancel");
        pendingPost = null;
      });
    }
    if (form) {
      form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        if (!pendingPost || !submitBtn || submitBtn.disabled) { return; }
        runConfirmedPost(pendingPost);
      });
    }
    if (phraseInput && submitBtn) {
      phraseInput.addEventListener("input", function () {
        var required = (pendingPost && pendingPost.confirmPhrase) || "";
        var ok = !required || phraseInput.value.trim() === required;
        submitBtn.disabled = !ok;
        if (errorEl) { errorEl.classList.add("d-none"); }
      });
    }
    return confirmDialog;
  }

  function openConfirmModal(opts) {
    var dlg = ensureConfirmDialog();
    if (!dlg) {
      if (window.confirm(opts.message)) {
        runConfirmedPost(opts);
      }
      return;
    }
    pendingPost = opts;
    var titleEl = dlg.querySelector("[data-rmc-bulk-confirm-title]");
    var msgEl = dlg.querySelector("[data-rmc-bulk-confirm-message]");
    var phraseWrap = dlg.querySelector("[data-rmc-bulk-confirm-phrase-wrap]");
    var phraseLabel = dlg.querySelector("[data-rmc-bulk-confirm-phrase-label]");
    var phraseInput = dlg.querySelector("[data-rmc-bulk-confirm-phrase-input]");
    var submitBtn = dlg.querySelector("[data-rmc-bulk-confirm-submit]");
    var errorEl = dlg.querySelector("[data-rmc-bulk-confirm-error]");

    if (titleEl) { titleEl.textContent = opts.title || "Confirm bulk action"; }
    if (msgEl) { msgEl.textContent = opts.message || ""; }
    if (errorEl) {
      errorEl.textContent = "";
      errorEl.classList.add("d-none");
    }
    if (phraseWrap && phraseInput && phraseLabel && submitBtn) {
      if (opts.confirmPhrase) {
        phraseWrap.hidden = false;
        phraseLabel.textContent = 'Type "' + opts.confirmPhrase + '" to confirm';
        phraseInput.value = "";
        phraseInput.placeholder = opts.confirmPhrase;
        submitBtn.disabled = true;
      } else {
        phraseWrap.hidden = true;
        phraseInput.value = "";
        submitBtn.disabled = false;
      }
    }
    if (typeof dlg.showModal === "function") {
      dlg.showModal();
    } else if (window.confirm(opts.message)) {
      runConfirmedPost(opts);
    }
  }

  function showBulkToast(message, tone) {
    document.dispatchEvent(
      new CustomEvent("rmc:bulk-action-complete", {
        bubbles: true,
        detail: { message: message, tone: tone || "success" },
      })
    );
    if (typeof window.showToast === "function") {
      window.showToast(message, tone || "success");
      return;
    }
    if (tone === "danger" && typeof window.alert === "function") {
      window.alert(message);
    }
  }

  // Canonical copilot URLs from the per-shell AI-chrome page-data island.
  // Present on every authenticated shell, so "Ask copilot" works even on pages
  // where the full copilot rail isn't rendered.
  function copilotUrls() {
    var el = document.getElementById("page-data-rmc-ai-chrome");
    if (!el || !el.textContent) { return {}; }
    try {
      var cfg = JSON.parse(el.textContent);
      return cfg.urls || {};
    } catch (_e) {
      return {};
    }
  }

  var SUPPORTS_FETCH_STREAM = (function () {
    try {
      return typeof ReadableStream === "function" &&
        typeof TextDecoder === "function" &&
        typeof fetch === "function";
    } catch (_e) { return false; }
  })();

  // --- Rich prompt construction -------------------------------------------
  // Turn the operator's selection into a structured, attribute-aware prompt so
  // the AI can give genuinely useful, specific advice instead of a platitude.
  function pageLensId() {
    var host = document.querySelector("[data-rmc-copilot-page-lens]");
    return host ? (host.getAttribute("data-rmc-copilot-page-lens") || "") : "";
  }

  function columnLabels(table) {
    var labels = [];
    table.querySelectorAll("thead th").forEach(function (th) {
      if (th.classList.contains("rmc-list-bulk-th")) { labels.push(null); return; }
      var t = (th.textContent || "").replace(/\s+/g, " ").trim();
      if (!t || t === "›" || /open detail/i.test(t)) { labels.push(null); return; }
      labels.push(t);
    });
    return labels;
  }

  function rowColumns(tr, labels, title) {
    var cells = tr.children;
    var out = {};
    for (var i = 0; i < cells.length && i < labels.length; i++) {
      var key = labels[i];
      if (!key) { continue; }
      var val = (cells[i].textContent || "").replace(/\s+/g, " ").trim();
      if (!val) { continue; }
      // Skip the name column — it duplicates the title (and concatenates the slug).
      if (title && val.indexOf(title) === 0) { continue; }
      out[key] = val;
    }
    return out;
  }

  function buildCopilotPrompt(table, items) {
    var labels = columnLabels(table);
    var lensId = pageLensId();
    var total = table.querySelectorAll("tbody [data-rmc-bulk-row]").length;
    var lines = items.map(function (it, idx) {
      var meta = {};
      try { meta = JSON.parse(it.row.getAttribute("data-rmc-row-meta") || "{}"); }
      catch (_e) { meta = {}; }
      var cols = rowColumns(it.row, labels, it.label);
      var combined = Object.assign({}, cols, meta); // curated row-meta wins
      var parts = Object.keys(combined).map(function (k) { return k + ": " + combined[k]; });
      var slug = it.slug ? " [" + it.slug + "]" : "";
      return (idx + 1) + ". " + it.label + slug + (parts.length ? " — " + parts.join(", ") : "");
    });
    var header = 'I\'m an operator on the "' + (lensId || "list") + '" page. I\'ve selected ' +
      items.length + " of " + total + " row(s) in a bulk table:";
    var ask = "Based on these specific records and their attributes, tell me: " +
      "(1) the most useful next actions I can take here, (2) anything that looks risky " +
      "or needs attention, (3) which bulk action to use. Be concise and operator-focused — no preamble.";
    return header + "\n" + lines.join("\n") + "\n\n" + ask;
  }

  // --- Answer modal (streaming) -------------------------------------------
  var copilotAnswerDialog = null;
  function ensureCopilotAnswerDialog() {
    if (copilotAnswerDialog) { return copilotAnswerDialog; }
    var dlg = document.createElement("dialog");
    dlg.className = "rmc-copilot-answer-dialog";
    dlg.setAttribute("data-rmc-copilot-answer-dialog", "1");
    dlg.innerHTML =
      '<form method="dialog" class="rmc-copilot-answer-dialog__inner">' +
        '<div class="rmc-copilot-answer-dialog__head">' +
          '<span class="rmc-copilot-answer-dialog__title">✦ Copilot</span>' +
          '<button type="submit" class="btn btn-sm btn-outline-secondary" ' +
            'data-rmc-copilot-answer-close aria-label="Close">×</button>' +
        '</div>' +
        '<p class="rmc-copilot-answer-dialog__prompt" data-rmc-copilot-answer-prompt></p>' +
        '<div class="rmc-copilot-answer-dialog__body" data-rmc-copilot-answer-body ' +
          'aria-live="polite"></div>' +
        '<div class="rmc-copilot-answer-dialog__actions" data-rmc-copilot-answer-actions></div>' +
      '</form>';
    document.body.appendChild(dlg);
    copilotAnswerDialog = dlg;
    return dlg;
  }

  // Render the page's destructive/mutating bulk actions as one-click follow-ups
  // so the operator can act on the AI's advice without re-finding the bulk bar.
  function renderCopilotFollowUps(dlg, table, items) {
    var host = dlg.querySelector("[data-rmc-copilot-answer-actions]");
    if (!host) { return; }
    host.innerHTML = "";
    parseActions(table).forEach(function (action) {
      if (action.kind !== "post") { return; }
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn btn-sm " +
        (action.variant === "danger" ? "btn-outline-danger" : "btn-outline-primary");
      btn.textContent = action.label || "Action";
      btn.addEventListener("click", function () {
        dlg.close();
        runAction(table, action, items);
      });
      host.appendChild(btn);
    });
  }

  // SSE frame parser — frames separated by a blank line per the spec.
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

  function copilotPostHeaders(accept) {
    return {
      Accept: accept,
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    };
  }

  function streamCopilotAnswer(streamUrl, prompt, bodyEl) {
    var assembled = "";
    var remainder = "";
    var sawDone = false;
    return fetch(streamUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: copilotPostHeaders("text/event-stream"),
      body: JSON.stringify({ message: prompt, mode: "operator" }),
    }).then(function (r) {
      if (!r.body || !r.body.getReader) { throw new Error("stream-unsupported"); }
      var reader = r.body.getReader();
      var decoder = new TextDecoder("utf-8");
      if (bodyEl) { bodyEl.textContent = ""; }
      function pump() {
        return reader.read().then(function (step) {
          if (step.done) {
            if (!sawDone && bodyEl && !assembled) { bodyEl.textContent = "(no reply)"; }
            return;
          }
          var parsed = parseSSEChunk(remainder, decoder.decode(step.value, { stream: true }));
          remainder = parsed.remainder;
          for (var i = 0; i < parsed.events.length; i++) {
            var ev = parsed.events[i];
            var payload = null;
            try { payload = JSON.parse(ev.data); } catch (_e) { payload = null; }
            if (!payload) { continue; }
            if (ev.name === "delta" && typeof payload.text === "string" && bodyEl) {
              assembled += payload.text;
              bodyEl.textContent = assembled;
            } else if (ev.name === "done") {
              sawDone = true;
              if (bodyEl && payload.reply) { bodyEl.textContent = payload.reply; }
            } else if (ev.name === "error" && bodyEl) {
              bodyEl.textContent = "The assistant returned an error.";
            }
          }
          return pump();
        });
      }
      return pump();
    });
  }

  function sendCopilotAnswerJSON(sendUrl, prompt, bodyEl) {
    return fetch(sendUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: copilotPostHeaders("application/json"),
      body: JSON.stringify({ message: prompt, mode: "operator" }),
    })
      .then(function (r) { return r.json().catch(function () { return null; }); })
      .then(function (data) {
        if (!bodyEl) { return; }
        bodyEl.textContent = (data && data.reply) ? data.reply : "AI is unavailable right now.";
      });
  }

  // Fallback path when the copilot rail isn't on the page: ask the gateway
  // directly (streaming when supported) and render the reply in a modal, with
  // one-click follow-up actions drawn from the page's own bulk actions.
  function askCopilotDirect(table, items, promptText) {
    var urls = copilotUrls();
    var sendUrl = urls.copilot_rail_send || "";
    var streamUrl = urls.copilot_rail_send_stream || "";
    if (!sendUrl && !streamUrl) {
      showBulkToast("Copilot isn't available on this page.", "warning");
      return;
    }
    var dlg = ensureCopilotAnswerDialog();
    var promptEl = dlg.querySelector("[data-rmc-copilot-answer-prompt]");
    var bodyEl = dlg.querySelector("[data-rmc-copilot-answer-body]");
    var names = items.map(function (i) { return i.label; }).filter(Boolean);
    var summary = items.length + " selected — " +
      names.slice(0, 6).join(", ") + (names.length > 6 ? "…" : "");
    if (promptEl) { promptEl.textContent = summary; }
    if (bodyEl) { bodyEl.textContent = "Thinking…"; }
    renderCopilotFollowUps(dlg, table, items);
    if (typeof dlg.showModal === "function" && !dlg.open) { dlg.showModal(); }

    var pipeline;
    if (SUPPORTS_FETCH_STREAM && streamUrl) {
      pipeline = streamCopilotAnswer(streamUrl, promptText, bodyEl).catch(function () {
        if (sendUrl) { return sendCopilotAnswerJSON(sendUrl, promptText, bodyEl); }
        throw new Error("no-fallback");
      });
    } else {
      pipeline = sendCopilotAnswerJSON(sendUrl || streamUrl, promptText, bodyEl);
    }
    pipeline.catch(function () {
      if (bodyEl) {
        bodyEl.textContent = "Couldn't reach the assistant. Check your connection and try again.";
      }
    });
  }

  function runConfirmedPost(opts) {
    var body = Object.assign({}, opts.payload || {}, { ids: opts.ids });
    if (opts.confirmPhrase) {
      body.confirm_phrase = opts.confirmPhrase;
    }
    fetch(opts.url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        Accept: "application/json",
      },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        return res.text().then(function (text) {
          var data = null;
          if (text) {
            try { data = JSON.parse(text); } catch (_e) { data = { ok: false, error: "Invalid server response." }; }
          }
          if (!res.ok) {
            throw new Error((data && data.error) || res.statusText || "Request failed");
          }
          return data || {};
        });
      })
      .then(function (data) {
        if (confirmDialog && typeof confirmDialog.close === "function") {
          confirmDialog.close();
        }
        pendingPost = null;
        var succeeded = data.succeeded != null ? data.succeeded : (data.ok ? 1 : 0);
        var processed = data.processed != null ? data.processed : opts.ids.length;
        var msg = succeeded + " of " + processed + " updated.";
        if (data.results) {
          var failures = data.results.filter(function (r) { return !r.ok; });
          if (failures.length) {
            msg += " " + failures.length + " failed.";
          }
        }
        showBulkToast(msg, data.ok ? "success" : "warning");
        if (opts.reload !== false) {
          var delay = parseInt(opts.reloadDelay, 10);
          if (isNaN(delay) || delay < 0) { delay = 600; }
          window.setTimeout(function () { window.location.reload(); }, delay);
        }
      })
      .catch(function (err) {
        var dlg = ensureConfirmDialog();
        var errorEl = dlg && dlg.querySelector("[data-rmc-bulk-confirm-error]");
        if (errorEl) {
          errorEl.textContent = err.message || "Request failed";
          errorEl.classList.remove("d-none");
          return;
        }
        showBulkToast(err.message || "Request failed", "danger");
      });
  }

  function emitBulkChange(table, items) {
    var labels = items.map(function (it) { return it.label; }).filter(Boolean);
    document.dispatchEvent(
      new CustomEvent("rmc:bulk-selection-changed", {
        bubbles: true,
        detail: {
          table: table,
          count: items.length,
          items: items,
          summary: labels.slice(0, 8).join(", ") + (labels.length > 8 ? "…" : ""),
        },
      })
    );
  }

  function updateBar(table) {
    var bar = getBar(table);
    if (!bar) { return; }
    var items = selectedRows(table).map(rowPayload);
    var countEl = bar.querySelector("[data-rmc-bulk-count]");
    if (countEl) {
      countEl.textContent = items.length + " selected";
    }
    bar.hidden = items.length === 0;
    table.querySelectorAll("tbody tr").forEach(function (tr) {
      var checked = !!tr.querySelector("[data-rmc-bulk-row]:checked");
      if (checked) { tr.setAttribute("data-rmc-bulk-selected", "1"); }
      else { tr.removeAttribute("data-rmc-bulk-selected"); }
    });
    var selectAll = table.querySelector("[data-rmc-bulk-select-all]");
    if (selectAll) {
      var boxes = table.querySelectorAll("tbody [data-rmc-bulk-row]");
      var checkedCount = selectedRows(table).length;
      selectAll.checked = boxes.length > 0 && checkedCount === boxes.length;
      selectAll.indeterminate = checkedCount > 0 && checkedCount < boxes.length;
    }
    emitBulkChange(table, items);
  }

  function interpolateConfirm(template, count) {
    return String(template || "Apply to {count} selected row(s)?").replace(/\{count\}/g, String(count));
  }

  function runAction(table, action, items) {
    if (!action || !action.kind) { return; }
    if (action.kind === "copilot" || action.id === "ask") {
      var prompt = buildCopilotPrompt(table, items);
      if (document.querySelector("[data-rmc-copilot-input]")) {
        // Rail is present — send through it so the reply lands in the threaded
        // copilot UI. (The lens already mirrors the selection via the
        // rmc:bulk-selection-changed event.)
        document.dispatchEvent(
          new CustomEvent("rmc:copilot-send-prompt", { bubbles: true, detail: { text: prompt } })
        );
      } else {
        // No rail on this surface — ask the gateway directly and show a
        // streaming answer in a modal, so the action is useful everywhere.
        askCopilotDirect(table, items, prompt);
      }
      return;
    }
    if (action.kind === "clipboard-slugs" || action.id === "copy-slugs") {
      var slugs = items.map(function (i) { return i.slug || i.value; }).join("\n");
      var plural = items.length === 1 ? "" : "s";
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(slugs).then(
          function () { showBulkToast("Copied " + items.length + " slug" + plural + " to clipboard.", "success"); },
          function () { showBulkToast("Couldn't copy to clipboard.", "danger"); }
        );
      } else {
        showBulkToast("Clipboard isn't available in this browser.", "warning");
      }
      return;
    }
    if (action.kind === "export-ids" || action.id === "export-selected") {
      var base = action.href || table.getAttribute("data-rmc-bulk-export-base") || "";
      if (!base) {
        showBulkToast("Export isn't configured for this list.", "warning");
        return;
      }
      var ids = items.map(function (i) { return i.value; }).join(",");
      var sep = base.indexOf("?") === -1 ? "?" : "&";
      showBulkToast("Exporting " + items.length + " row" + (items.length === 1 ? "" : "s") + "…", "success");
      window.location.href = base + sep + "ids=" + encodeURIComponent(ids) + "&format=csv";
      return;
    }
    if (action.kind === "post" && action.url) {
      var payload = action.payload || {};
      if (action.action) { payload.action = action.action; }
      openConfirmModal({
        title: action.confirmTitle || action.label || "Confirm",
        message: interpolateConfirm(action.confirm, items.length),
        confirmPhrase: action.confirmPhrase || "",
        url: action.url,
        ids: items.map(function (i) { return i.value; }),
        payload: payload,
        reload: action.reload !== false,
        reloadDelay: action.reloadDelay,
      });
      return;
    }
    if (action.kind === "navigate" && action.href) {
      window.location.href = action.href;
    }
  }

  function renderActionButtons(table, bar) {
    var host = bar.querySelector("[data-rmc-bulk-actions-host]");
    if (!host) { return; }
    var actions = parseActions(table);
    host.innerHTML = "";
    actions.forEach(function (action) {
      var btn = document.createElement("button");
      btn.type = "button";
      var variant = action.variant || "outline-primary";
      if (variant === "danger") {
        btn.className = "btn btn-sm btn-outline-danger";
      } else if (variant === "primary") {
        btn.className = "btn btn-sm btn-primary";
      } else {
        btn.className = "btn btn-sm btn-outline-primary";
      }
      btn.textContent = action.label || "Action";
      btn.addEventListener("click", function () {
        var items = selectedRows(table).map(rowPayload);
        if (!items.length) { return; }
        runAction(table, action, items);
      });
      host.appendChild(btn);
    });
  }

  function bindTable(table) {
    if (table.getAttribute("data-rmc-list-bulk-bound") === "1") { return; }
    table.setAttribute("data-rmc-list-bulk-bound", "1");
    var bar = getBar(table);
    if (bar) { renderActionButtons(table, bar); }

    table.addEventListener("change", function (ev) {
      var t = ev.target;
      if (!t) { return; }
      if (t.matches("[data-rmc-bulk-row]") || t.matches("[data-rmc-bulk-select-all]")) {
        if (t.matches("[data-rmc-bulk-select-all]")) {
          var on = t.checked;
          table.querySelectorAll("tbody [data-rmc-bulk-row]").forEach(function (cb) {
            cb.checked = on;
          });
        }
        ev.stopPropagation();
        updateBar(table);
      }
    });

    if (bar) {
      var clearBtn = bar.querySelector("[data-rmc-bulk-clear]");
      if (clearBtn) {
        clearBtn.addEventListener("click", function () {
          table.querySelectorAll("[data-rmc-bulk-row], [data-rmc-bulk-select-all]").forEach(function (el) {
            el.checked = false;
            el.indeterminate = false;
          });
          updateBar(table);
        });
      }
    }
  }

  function init() {
    ensureConfirmDialog();
    document.querySelectorAll('table[data-rmc-list-bulk="1"]').forEach(bindTable);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
