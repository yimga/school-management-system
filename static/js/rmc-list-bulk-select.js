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
      var names = items.map(function (i) { return i.label; }).join(", ");
      var prompt = "I selected " + items.length + " row(s): " + names + ". What should I do next on this page?";
      document.dispatchEvent(
        new CustomEvent("rmc:copilot-lens-prompt", { bubbles: true, detail: { text: prompt } })
      );
      return;
    }
    if (action.kind === "clipboard-slugs" || action.id === "copy-slugs") {
      var slugs = items.map(function (i) { return i.slug || i.value; }).join("\n");
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(slugs);
      }
      return;
    }
    if (action.kind === "export-ids" || action.id === "export-selected") {
      var base = action.href || table.getAttribute("data-rmc-bulk-export-base") || "";
      if (!base) { return; }
      var ids = items.map(function (i) { return i.value; }).join(",");
      var sep = base.indexOf("?") === -1 ? "?" : "&";
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
