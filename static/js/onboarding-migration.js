/**
 * Onboarding migration interactive bits.
 *  - Vendor tile click: toggles hidden radio + visual selected state.
 *  - Domain checklist: live tally of selected count + estimated minutes.
 *
 * Vanilla, no deps, ~2KB. Guards every DOM op so partial markup never throws.
 */
(function () {
  "use strict";

  // ─── Vendor picker (wizard step 3) ────────────────────────────────────
  function wireVendorTiles() {
    var tiles = document.querySelectorAll(".ovendor-tile[data-vendor-slug]");
    if (!tiles.length) return;
    var hidden = document.getElementById("vendor-selected-slug");
    var submitBtn = document.getElementById("vendor-continue-btn");
    var submitLabel = document.getElementById("vendor-continue-label");
    var defaultLabel = (submitLabel && submitLabel.dataset.defaultLabel) || "Continue";

    function selectTile(t) {
      tiles.forEach(function (el) {
        var isSelected = el === t;
        el.classList.toggle("is-selected", isSelected);
        // Role="radio" requires aria-checked (not aria-pressed). Both attrs
        // are kept in sync so the DOM remains valid whichever role consumers
        // expect — but screen readers go through aria-checked.
        el.setAttribute("aria-checked", isSelected ? "true" : "false");
        el.tabIndex = isSelected ? 0 : -1;
      });
      if (hidden) hidden.value = t.dataset.vendorSlug || "";
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.classList.remove("disabled");
      }
      if (submitLabel) {
        var name = t.dataset.vendorName || defaultLabel;
        submitLabel.textContent = "Continue with " + name;
      }
    }

    var hasSelection = false;
    tiles.forEach(function (tile) {
      tile.setAttribute("role", "radio");
      var preSelected = tile.classList.contains("is-selected");
      if (preSelected) hasSelection = true;
      tile.setAttribute("aria-checked", preSelected ? "true" : "false");
      tile.tabIndex = preSelected ? 0 : -1;
      tile.addEventListener("click", function (e) {
        e.preventDefault();
        selectTile(tile);
      });
      tile.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          selectTile(tile);
        } else if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          e.preventDefault();
          var next = tile.nextElementSibling;
          while (next && !next.classList.contains("ovendor-tile")) next = next.nextElementSibling;
          if (next) { selectTile(next); next.focus(); }
        } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
          e.preventDefault();
          var prev = tile.previousElementSibling;
          while (prev && !prev.classList.contains("ovendor-tile")) prev = prev.previousElementSibling;
          if (prev) { selectTile(prev); prev.focus(); }
        }
      });
    });
    // If nothing is pre-selected, the first tile is the keyboard entry point
    // so Tab can land in the radiogroup without selecting anything.
    if (!hasSelection && tiles[0]) tiles[0].tabIndex = 0;
  }

  // ─── Domain checklist (post-verify handoff) ──────────────────────────
  function wireDomainChecklist() {
    var checks = document.querySelectorAll(".omig-domain__check");
    if (!checks.length) return;
    var countEl = document.getElementById("omig-tally-count");
    var minutesEl = document.getElementById("omig-tally-minutes");

    function update() {
      var n = 0;
      var minutes = 0;
      checks.forEach(function (c) {
        if (c.checked) {
          n++;
          var m = parseInt(c.dataset.minutes || "0", 10);
          if (!isNaN(m)) minutes += m;
        }
      });
      if (countEl) countEl.textContent = String(n);
      if (minutesEl) minutesEl.textContent = String(minutes);
    }

    checks.forEach(function (c) {
      c.addEventListener("change", update);
    });
    update();
  }

  function init() {
    try { wireVendorTiles(); } catch (e) { /* never block paint */ }
    try { wireDomainChecklist(); } catch (e) { /* never block paint */ }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
