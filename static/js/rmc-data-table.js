/**
 * Platform-wide table density toggle for .rmc-data-table.
 *
 * Markup contract (legacy Condensed/Expanded OR Compact/Cozy/Roomy values):
 *   <div class="rmc-table-density-toggle" data-rmc-table-target="my-table">
 *     <button class="btn" data-density="compact">Compact</button>
 *     <button class="btn" data-density="comfortable">Cozy</button>
 *     <button class="btn" data-density="spacious">Roomy</button>
 *   </div>
 *   <table id="my-table" class="rmc-data-table">…</table>
 *
 * Also binds `.table-density-toggle` (finance/evals markup) so those pages
 * speak the same vocabulary. Aliases: condensed→compact, expanded→spacious,
 * cozy→comfortable, roomy→spacious, default→comfortable.
 *
 * Choice persists per target via localStorage so each table remembers.
 */
(function () {
  "use strict";
  var STORAGE_PREFIX = "rmc-table-density:";
  var DENSITY_CLASSES = ["table-density-compact", "table-density-comfortable", "table-density-spacious"];
  var ALIASES = {
    compact: "compact", condensed: "compact",
    comfortable: "comfortable", cozy: "comfortable", default: "comfortable",
    spacious: "spacious", expanded: "spacious", roomy: "spacious"
  };

  function normalize(density) {
    var key = String(density || "").toLowerCase().trim();
    return ALIASES[key] || "comfortable";
  }

  function applyDensity(table, density) {
    if (!table) { return; }
    var d = normalize(density);
    table.setAttribute("data-density", d);
    DENSITY_CLASSES.forEach(function (cls) { table.classList.remove(cls); });
    table.classList.add("table-density-" + d);
  }

  function syncButtons(toggle, density) {
    var d = normalize(density);
    toggle.querySelectorAll("[data-density]").forEach(function (btn) {
      var btnD = normalize(btn.getAttribute("data-density"));
      var active = btnD === d;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function bindToggle(toggle) {
    if (toggle.getAttribute("data-rmc-density-bound") === "1") { return; }
    toggle.setAttribute("data-rmc-density-bound", "1");
    var targetId = toggle.getAttribute("data-rmc-table-target");
    var key = STORAGE_PREFIX + (targetId || toggle.id || "default");
    var table = targetId
      ? document.getElementById(targetId)
      : (toggle.closest(".card, .rmc-panel, section, form, .table-responsive") || toggle.parentElement)
          .querySelector(".rmc-data-table, table.table-family");
    if (!table && toggle.parentElement) {
      table = toggle.parentElement.querySelector(".rmc-data-table, table.table-family");
    }
    if (!table) {
      // finance/evals: toggle sits above a sibling wrapper that holds the table
      var sib = toggle.nextElementSibling;
      while (sib && !table) {
        table = sib.querySelector && sib.querySelector(".rmc-data-table, table.table-family");
        sib = sib.nextElementSibling;
      }
    }
    if (!table) { return; }
    var stored = null;
    try { stored = localStorage.getItem(key); } catch (_) {}
    var initial = stored || table.getAttribute("data-density") || "comfortable";
    applyDensity(table, initial);
    syncButtons(toggle, initial);
    toggle.addEventListener("click", function (e) {
      var btn = e.target.closest && e.target.closest("[data-density]");
      if (!btn || !toggle.contains(btn)) { return; }
      e.preventDefault();
      var d = btn.getAttribute("data-density");
      applyDensity(table, d);
      syncButtons(toggle, d);
      try { localStorage.setItem(key, normalize(d)); } catch (_) {}
    });
  }

  function init() {
    document.querySelectorAll(".rmc-table-density-toggle, .table-density-toggle").forEach(bindToggle);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
