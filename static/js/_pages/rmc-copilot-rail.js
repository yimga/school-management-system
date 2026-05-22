/* ============================================================
   rmc-copilot-rail.js — v3.55.0+ (2026-05-21)
   ------------------------------------------------------------
   AI Copilot rail expand/collapse + Cmd/Ctrl+K focus.

   Toggles [data-copilot] between "collapsed" and "expanded" on the
   nearest .rmc-app-shell ancestor of any [data-rmc-copilot-toggle]
   button. Cmd/Ctrl+K shifts focus to the textarea inside the rail
   (auto-expands if collapsed). Idempotent — runs once per page even
   if the script is loaded twice.

   No external dependencies. CSP-safe (no inline handlers).
   ============================================================ */
(function () {
  "use strict";

  if (typeof document === "undefined") { return; }
  if (document.documentElement.dataset.rmcCopilotInited === "1") { return; }
  document.documentElement.dataset.rmcCopilotInited = "1";

  function findShell(el) {
    while (el && el !== document.body) {
      if (el.classList && el.classList.contains("rmc-app-shell")) {
        return el;
      }
      el = el.parentElement;
    }
    return document.querySelector(".rmc-app-shell");
  }

  function setState(shell, state) {
    if (!shell) { return; }
    shell.setAttribute("data-copilot", state);
  }

  function toggleShell(shell) {
    if (!shell) { return; }
    var current = shell.getAttribute("data-copilot") || "collapsed";
    setState(shell, current === "expanded" ? "collapsed" : "expanded");
  }

  function focusInput(shell) {
    if (!shell) { return; }
    setState(shell, "expanded");
    var input = shell.querySelector("[data-rmc-copilot-input]");
    if (input && typeof input.focus === "function") {
      // Defer focus one tick so the expanded panel has rendered.
      window.setTimeout(function () { input.focus(); }, 0);
    }
  }

  function findNotebook() {
    return document.querySelector("[data-rmc-operator-notebook]");
  }

  function toggleNotebookMinimized() {
    var nb = findNotebook();
    if (!nb) { return; }
    var current = nb.getAttribute("data-rmc-notebook-state") || "open";
    nb.setAttribute("data-rmc-notebook-state", current === "minimized" ? "open" : "minimized");
  }

  function onClick(ev) {
    var target = ev.target;
    if (!target || typeof target.closest !== "function") { return; }

    /* Notebook minimize (the ─ button inside the notebook head) and the
       pencil-icon on the collapsed copilot rail both toggle the notebook. */
    var nbMinBtn = target.closest(".lx-notebook__min");
    var nbToggleBtn = target.closest("[data-rmc-operator-notebook-toggle]");
    if (nbMinBtn || nbToggleBtn) {
      ev.preventDefault();
      toggleNotebookMinimized();
      return;
    }

    var toggle = target.closest("[data-rmc-copilot-toggle]");
    if (!toggle) { return; }
    ev.preventDefault();
    toggleShell(findShell(toggle));
  }

  function onKeydown(ev) {
    var key = (ev.key || "").toLowerCase();
    if (key !== "k") { return; }
    if (!(ev.metaKey || ev.ctrlKey)) { return; }
    if (ev.altKey || ev.shiftKey) { return; }
    var rail = document.querySelector("[data-rmc-copilot-rail]");
    if (!rail) { return; }
    ev.preventDefault();
    focusInput(findShell(rail));
  }

  document.addEventListener("click", onClick, false);
  document.addEventListener("keydown", onKeydown, false);
})();
