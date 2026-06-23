/*
 * rmc-modal-intelligence.js — Surface 7: declarative + programmatic confirm.
 *
 * The platform already has a premium native-<dialog> sheet system
 * (rmc-bottom-sheet.js / window.RMCSheet + the .rmc-sheet grammar): focus-trap,
 * ESC, backdrop-click, drag-to-dismiss, and a responsive bottom-sheet→centered-
 * dialog treatment — plus 47 Bootstrap modals. What's missing is the connective
 * tissue for the most common modal of all: the destructive-action confirm.
 * Today ~35 JS files call the raw browser confirm()/alert() — unstyleable,
 * un-branded, inaccessible, and tab-blocking.
 *
 * This engine COMPOSES the existing sheet system (it builds ONE pooled
 * <dialog class="rmc-sheet"> and opens it through window.RMCSheet so it inherits
 * every a11y behaviour for free) and exposes two replacements:
 *
 *   - Declarative: any element with [data-rmc-confirm="message"] is intercepted;
 *     the styled confirm renders, and only on confirm is the original action
 *     re-run (submit / navigate / onclick) — no per-page JS.
 *   - Programmatic: window.RMCConfirm(opts) -> Promise<bool> and
 *     window.RMCAlert(opts) -> Promise<void> drop-in replacements that page JS
 *     adopts in a single line (`if (await RMCConfirm({...})) { ... }`).
 *
 * Danger guard: destructive intents (tone="danger") get a red confirm button
 * and focus defaults to Cancel so a stray Enter can't fire the destructive path.
 *
 * Config comes from the #rmc-modal-config island (SITE cascade, default-on).
 * CSP-safe: every node is createElement + textContent. Self-guarded; no-op when
 * its hooks are absent. The Bootstrap modals + existing rmc-sheet callers are
 * untouched.
 */
(function () {
  "use strict";

  if (window.__rmcModalIntelligenceInit) {
    return;
  }
  window.__rmcModalIntelligenceInit = true;

  function readConfig() {
    var el = document.getElementById("rmc-modal-config");
    if (!el) {
      return { intelligence: true, confirm: true, dangerGuard: true };
    }
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (e) {
      return { intelligence: true, confirm: true, dangerGuard: true };
    }
  }

  var cfg = readConfig();
  if (cfg.intelligence === false) {
    return;
  }

  var DIALOG_ID = "rmc-confirm-dialog";
  var passing = typeof WeakSet === "function" ? new WeakSet() : null;

  // ---- The pooled confirm dialog (built once, reused) ----------------------
  var refs = null;

  function buildDialog() {
    var dlg = document.createElement("dialog");
    dlg.className = "rmc-sheet rmc-sheet--sm rmc-confirm";
    dlg.id = DIALOG_ID;
    dlg.setAttribute("role", "alertdialog");
    dlg.setAttribute("aria-modal", "true");
    dlg.setAttribute("aria-labelledby", DIALOG_ID + "-title");
    dlg.setAttribute("aria-describedby", DIALOG_ID + "-body");

    var header = document.createElement("header");
    header.className = "rmc-sheet__header";

    var icon = document.createElement("span");
    icon.className = "rmc-sheet__icon rmc-confirm__icon";
    icon.setAttribute("aria-hidden", "true");
    var iconI = document.createElement("i");
    iconI.className = "bi bi-question-circle";
    icon.appendChild(iconI);

    var group = document.createElement("div");
    group.className = "rmc-sheet__title-group";
    var title = document.createElement("h3");
    title.className = "rmc-sheet__title";
    title.id = DIALOG_ID + "-title";
    var subtitle = document.createElement("p");
    subtitle.className = "rmc-sheet__subtitle rmc-confirm__subtitle";
    subtitle.hidden = true;
    group.appendChild(title);
    group.appendChild(subtitle);

    header.appendChild(icon);
    header.appendChild(group);

    var body = document.createElement("div");
    body.className = "rmc-sheet__body rmc-confirm__body";
    body.id = DIALOG_ID + "-body";

    var footer = document.createElement("footer");
    footer.className = "rmc-sheet__footer";
    var cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.className = "btn btn-secondary rmc-confirm__cancel";
    var okBtn = document.createElement("button");
    okBtn.type = "button";
    okBtn.className = "btn btn-primary rmc-confirm__ok";
    footer.appendChild(cancelBtn);
    footer.appendChild(okBtn);

    dlg.appendChild(header);
    dlg.appendChild(body);
    dlg.appendChild(footer);
    document.body.appendChild(dlg);

    refs = {
      dialog: dlg,
      icon: iconI,
      title: title,
      subtitle: subtitle,
      body: body,
      cancel: cancelBtn,
      ok: okBtn,
    };
    return refs;
  }

  function ensureDialog() {
    if (refs && document.body.contains(refs.dialog)) {
      return refs;
    }
    return buildDialog();
  }

  function openSheet(dlg) {
    if (window.RMCSheet && typeof window.RMCSheet.open === "function") {
      window.RMCSheet.open(dlg);
      if (dlg.hasAttribute("open")) {
        return;
      }
    }
    if (typeof dlg.showModal === "function" && !dlg.hasAttribute("open")) {
      try {
        dlg.showModal();
        return;
      } catch (e) {
        /* fall through */
      }
    }
    dlg.setAttribute("open", "open");
  }

  function closeSheet(dlg) {
    if (window.RMCSheet && typeof window.RMCSheet.close === "function") {
      window.RMCSheet.close(dlg);
    } else if (typeof dlg.close === "function" && dlg.hasAttribute("open")) {
      dlg.close();
    } else {
      dlg.removeAttribute("open");
    }
  }

  // ---- Core: open a confirm, resolve true/false ----------------------------
  // opts: { title, message, ok, cancel, tone: "default"|"danger", icon, alert }
  function openConfirm(opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      var r;
      try {
        r = ensureDialog();
      } catch (e) {
        // Last-ditch fallback so a destructive action is never silently allowed.
        resolve(window.confirm(opts.message || opts.title || "Are you sure?"));
        return;
      }

      var danger = opts.tone === "danger";
      var isAlert = opts.alert === true;

      r.title.textContent = opts.title || (isAlert ? "Notice" : "Please confirm");
      r.body.textContent = opts.message || "";
      if (opts.subtitle) {
        r.subtitle.textContent = opts.subtitle;
        r.subtitle.hidden = false;
      } else {
        r.subtitle.textContent = "";
        r.subtitle.hidden = true;
      }
      r.icon.className =
        "bi " +
        (opts.icon ||
          (danger ? "bi-exclamation-triangle-fill" : isAlert ? "bi-info-circle-fill" : "bi-question-circle"));
      r.dialog.setAttribute("data-rmc-confirm-tone", danger ? "danger" : "default");

      r.ok.textContent = opts.ok || (isAlert ? "OK" : "Confirm");
      r.ok.className =
        "btn rmc-confirm__ok " + (danger ? "btn-danger" : "btn-primary");
      r.cancel.textContent = opts.cancel || "Cancel";
      r.cancel.hidden = isAlert; // alert() has no cancel

      var settled = false;
      function settle(value) {
        if (settled) {
          return;
        }
        settled = true;
        r.ok.removeEventListener("click", onOk);
        r.cancel.removeEventListener("click", onCancel);
        r.dialog.removeEventListener("close", onClose);
        closeSheet(r.dialog);
        resolve(value);
      }
      function onOk() {
        settle(isAlert ? undefined : true);
      }
      function onCancel() {
        settle(isAlert ? undefined : false);
      }
      function onClose() {
        // ESC / backdrop / × all route through the native close event.
        settle(isAlert ? undefined : false);
      }

      r.ok.addEventListener("click", onOk);
      r.cancel.addEventListener("click", onCancel);
      r.dialog.addEventListener("close", onClose);

      openSheet(r.dialog);

      // Danger guard: when on, focus defaults to Cancel so a stray Enter can't
      // fire the destructive path; otherwise focus the primary action.
      try {
        if (danger && cfg.dangerGuard !== false && !r.cancel.hidden) {
          r.cancel.focus();
        } else {
          r.ok.focus();
        }
      } catch (e) {
        /* focus is best-effort */
      }
    });
  }

  // ---- Declarative [data-rmc-confirm] interception -------------------------
  function optsFromEl(el) {
    return {
      message: el.getAttribute("data-rmc-confirm") || "",
      title: el.getAttribute("data-rmc-confirm-title") || "",
      subtitle: el.getAttribute("data-rmc-confirm-subtitle") || "",
      ok: el.getAttribute("data-rmc-confirm-ok") || "",
      cancel: el.getAttribute("data-rmc-confirm-cancel") || "",
      tone: el.getAttribute("data-rmc-confirm-tone") || "default",
      icon: el.getAttribute("data-rmc-confirm-icon") || "",
    };
  }

  function reRun(el) {
    // Re-dispatch the element's native default now that it's confirmed. A
    // single passing-guard prevents the delegate from re-intercepting it:
    // el.click() submits a submit-button's form, navigates an <a href>, or
    // fires an onclick — one path covers them all.
    if (passing) {
      passing.add(el);
    }
    try {
      el.click();
    } finally {
      if (passing) {
        window.setTimeout(function () {
          passing.delete(el);
        }, 0);
      }
    }
  }

  function onDelegatedClick(ev) {
    if (cfg.confirm === false) {
      return;
    }
    // Only intercept a plain primary click (let ctrl/cmd/middle open new tabs).
    if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) {
      return;
    }
    var el = ev.target && ev.target.closest ? ev.target.closest("[data-rmc-confirm]") : null;
    if (!el) {
      return;
    }
    if (passing && passing.has(el)) {
      return; // this is the re-dispatched, already-confirmed click
    }
    var message = el.getAttribute("data-rmc-confirm");
    if (!message) {
      return;
    }
    ev.preventDefault();
    ev.stopPropagation();
    if (ev.stopImmediatePropagation) {
      ev.stopImmediatePropagation();
    }
    openConfirm(optsFromEl(el)).then(function (ok) {
      if (ok) {
        reRun(el);
      }
    });
  }

  // ---- Public API ----------------------------------------------------------
  window.RMCConfirm = function (opts) {
    if (typeof opts === "string") {
      opts = { message: opts };
    }
    return openConfirm(opts || {});
  };
  window.RMCAlert = function (opts) {
    if (typeof opts === "string") {
      opts = { message: opts };
    }
    opts = opts || {};
    opts.alert = true;
    return openConfirm(opts);
  };
  window.RMCModal = {
    confirm: window.RMCConfirm,
    alert: window.RMCAlert,
    open: function (idOrEl) {
      if (window.RMCSheet && window.RMCSheet.open) {
        return window.RMCSheet.open(idOrEl);
      }
    },
    close: function (idOrEl) {
      if (window.RMCSheet && window.RMCSheet.close) {
        return window.RMCSheet.close(idOrEl);
      }
    },
  };

  function init() {
    try {
      // Capture phase so we intercept before the element's own handlers run.
      document.addEventListener("click", onDelegatedClick, true);
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
