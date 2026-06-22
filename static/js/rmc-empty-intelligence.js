/**
 * RunMyCampus Empty-State Intelligence (v4.04.62) — Surface 4.
 *
 * Two things live here; the third (the TWO table empty states) rides the table
 * engine where the filter logic already lives (see rmc-table-intelligence.js):
 *
 *   1. Adopt-everywhere: upgrade any opt-in [data-rmc-empty] container into the
 *      canonical .rmc-empty look (icon + title + message + optional CTAs) from
 *      its data-* attributes — so a page can get a first-class empty state
 *      without hand-writing the component markup, and existing bare empty
 *      blocks can be elevated by adding one attribute.
 *
 * Config (default-on) comes from the #rmc-empty-config island (SITE cascade).
 * CSP-safe: createElement + textContent only, never innerHTML of runtime data.
 * Wrapped in try/catch; no-ops when there's nothing to enhance.
 */
(function () {
  "use strict";

  var cfg = { intelligence: true, adopt: true };

  function readConfig() {
    var node = document.getElementById("rmc-empty-config");
    if (!node || !node.textContent) { return; }
    try {
      var d = JSON.parse(node.textContent);
      ["intelligence", "adopt"].forEach(function (k) {
        if (d[k] === false || d[k] === 0 || d[k] === "0") { cfg[k] = false; }
      });
    } catch (_) {}
  }

  function appendAction(actions, url, label, variant) {
    if (!url || !label) { return; }
    var a = document.createElement("a");
    a.className = "btn " + variant;
    a.setAttribute("href", url);
    a.textContent = label;
    actions.appendChild(a);
  }

  function adopt(el) {
    if (el.dataset.rmcEmptyReady === "1") { return; }
    el.dataset.rmcEmptyReady = "1";
    // Never clobber a container that already carries built markup (server CTAs,
    // localized rich text, icons) — only fill genuinely-empty opt-in shells.
    if (el.children && el.children.length > 0) { return; }

    var icon = el.getAttribute("data-empty-icon") || "bi-inbox";
    var title = el.getAttribute("data-empty-title") || "";
    var message = el.getAttribute("data-empty-message") || "";
    var ctaUrl = el.getAttribute("data-empty-cta-url");
    var ctaLabel = el.getAttribute("data-empty-cta-label");
    var secUrl = el.getAttribute("data-empty-secondary-url");
    var secLabel = el.getAttribute("data-empty-secondary-label");

    el.classList.add("rmc-empty");
    el.setAttribute("role", "status");
    el.textContent = "";  // replace any bare placeholder text

    var ic = document.createElement("div");
    ic.className = "rmc-empty__icon";
    ic.setAttribute("aria-hidden", "true");
    var i = document.createElement("i");
    i.className = "bi " + icon;
    ic.appendChild(i);
    el.appendChild(ic);

    if (title) {
      var h = document.createElement("h3");
      h.className = "rmc-empty__title";
      h.textContent = title;
      el.appendChild(h);
    }
    if (message) {
      var p = document.createElement("p");
      p.className = "rmc-empty__message";
      p.textContent = message;
      el.appendChild(p);
    }
    if ((ctaUrl && ctaLabel) || (secUrl && secLabel)) {
      var actions = document.createElement("div");
      actions.className = "rmc-empty__actions";
      appendAction(actions, ctaUrl, ctaLabel, "btn-primary");
      appendAction(actions, secUrl, secLabel, "btn-outline-secondary");
      el.appendChild(actions);
    }
  }

  function init() {
    readConfig();
    if (!cfg.intelligence || !cfg.adopt) { return; }
    var nodes = document.querySelectorAll("[data-rmc-empty]");
    Array.prototype.forEach.call(nodes, function (el) { try { adopt(el); } catch (_) {} });
    window.RMCEmptyIntelligence = { adopt: adopt };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
