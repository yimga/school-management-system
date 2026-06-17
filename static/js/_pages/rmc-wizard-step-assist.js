/**
 * rmc-wizard-step-assist.js — per-step "Ask about this step" copilot.
 *
 * Turns the wizard help rail into a scoped AI helper. Reuses the working tenant
 * copilot endpoint (portal:copilot_rail_send) and prepends the current step's
 * context so the answer is about THIS step — distinct from the general floating
 * copilot rail. Degrades silently: no endpoint / no AI => the rest of the help
 * rail is unaffected.
 *
 * CSP-safe IIFE, no inline handlers. The endpoint already RBAC-gates + grounds
 * the request in onboarding state server-side.
 */
(function () {
  "use strict";
  if (typeof document === "undefined") { return; }

  function csrfToken(root) {
    var hidden = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (hidden && hidden.value) { return hidden.value; }
    var meta = document.querySelector("meta[name=csrf-token]");
    return meta ? (meta.getAttribute("content") || "") : "";
  }

  function buildMessage(root, question) {
    var stepLabel = root.getAttribute("data-step-label") || "";
    var wizard = root.getAttribute("data-wizard") || "";
    var ctx = [];
    if (stepLabel) { ctx.push('the "' + stepLabel + '" step'); }
    if (wizard) { ctx.push("the " + wizard.replace(/_/g, " ") + " setup wizard"); }
    var prefix = ctx.length ? "I'm on " + ctx.join(" of ") + ". " : "";
    return prefix + question;
  }

  function setReply(replyEl, text, busy) {
    if (!replyEl) { return; }
    replyEl.hidden = false;
    replyEl.textContent = text;
    if (busy) { replyEl.setAttribute("data-busy", "1"); }
    else { replyEl.removeAttribute("data-busy"); }
  }

  function wire(root) {
    var endpoint = root.getAttribute("data-endpoint") || "";
    if (!endpoint) { return; }  // operator host / unconfigured — no-op
    var form = root.querySelector("[data-rmc-wizard-assist-form]");
    var input = root.querySelector("[data-rmc-wizard-assist-input]");
    var sendBtn = root.querySelector("[data-rmc-wizard-assist-send]");
    var reply = root.querySelector("[data-rmc-wizard-assist-reply]");
    if (!form || !input) { return; }

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var question = (input.value || "").trim();
      if (!question) { input.focus(); return; }
      if (sendBtn) { sendBtn.disabled = true; }
      setReply(reply, "Thinking…", true);

      fetch(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(root),
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({ message: buildMessage(root, question) })
      }).then(function (r) {
        return r.json().then(function (data) { return { ok: r.ok, data: data }; });
      }).then(function (res) {
        var data = res.data || {};
        var text = data.reply || (res.ok
          ? "I didn't have a useful answer for that — try rephrasing."
          : "The assistant is unavailable right now. The steps on the left walk you through it.");
        setReply(reply, text, false);
      }).catch(function () {
        setReply(reply, "Couldn't reach the assistant. Check your connection and try again.", false);
      }).then(function () {
        if (sendBtn) { sendBtn.disabled = false; }
      });
    });
  }

  function init() {
    var roots = document.querySelectorAll("[data-rmc-wizard-assist]");
    for (var i = 0; i < roots.length; i++) { wire(roots[i]); }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
