/**
 * Platform-wide table density toggle for .rmc-data-table.
 *
 * Markup contract:
 *   <div class="rmc-table-density-toggle" data-rmc-table-target="my-table">
 *     <button class="btn" data-density="condensed">Condensed</button>
 *     <button class="btn" data-density="default">Default</button>
 *     <button class="btn" data-density="expanded">Expanded</button>
 *   </div>
 *   <table id="my-table" class="rmc-data-table">…</table>
 *
 * Choice persists per target via localStorage so each table remembers.
 */
(function () {
  "use strict";
  var STORAGE_PREFIX = "rmc-table-density:";

  function applyDensity(table, density) {
    if (!table) { return; }
    if (density && density !== "default") {
      table.setAttribute("data-density", density);
    } else {
      table.removeAttribute("data-density");
    }
  }

  function syncButtons(toggle, density) {
    toggle.querySelectorAll("[data-density]").forEach(function (btn) {
      var active = (btn.getAttribute("data-density") === density) ||
                   (density === "default" && btn.getAttribute("data-density") === "default");
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }

  function init() {
    var toggles = document.querySelectorAll(".rmc-table-density-toggle");
    toggles.forEach(function (toggle) {
      var targetId = toggle.getAttribute("data-rmc-table-target");
      var key = STORAGE_PREFIX + (targetId || toggle.id || "default");
      var table = targetId ? document.getElementById(targetId) : toggle.parentElement.querySelector(".rmc-data-table");
      if (!table) { return; }
      var stored = null;
      try { stored = localStorage.getItem(key); } catch (_) {}
      var initial = stored || "default";
      applyDensity(table, initial);
      syncButtons(toggle, initial);
      toggle.addEventListener("click", function (e) {
        var btn = e.target.closest && e.target.closest("[data-density]");
        if (!btn) { return; }
        e.preventDefault();
        var d = btn.getAttribute("data-density");
        applyDensity(table, d);
        syncButtons(toggle, d);
        try { localStorage.setItem(key, d); } catch (_) {}
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
