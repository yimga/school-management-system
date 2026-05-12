/**
 * Deterministic avatar gradient picker.
 *
 * Hashes [data-rmc-avatar-seed] to one of 10 curated gradient pairs and sets
 *   --rmc-avatar-grad-from / --rmc-avatar-grad-to
 * on each `.rmc-avatar`. Avatars with a profile photo keep their photo; the
 * gradient only shows when initials are visible.
 *
 * Curated pairs follow Apple SF color hues — saturated enough to be lively but
 * neutral-warm enough not to clash with any tenant brand.
 */
(function () {
  "use strict";

  var PALETTES = [
    ["#FF453A", "#FF9F0A"], // red → orange
    ["#FF9F0A", "#FFD60A"], // orange → yellow
    ["#FFD60A", "#30D158"], // yellow → green
    ["#30D158", "#5AC8FA"], // green → cyan
    ["#5AC8FA", "#0A84FF"], // cyan → blue
    ["#0A84FF", "#5E5CE6"], // blue → indigo
    ["#5E5CE6", "#BF5AF2"], // indigo → purple
    ["#BF5AF2", "#FF375F"], // purple → pink
    ["#FF375F", "#FF453A"], // pink → red
    ["#64D2FF", "#0A84FF"], // light blue → blue
  ];

  function hashSeed(seed) {
    var s = String(seed || "");
    var hash = 0;
    for (var i = 0; i < s.length; i++) {
      hash = ((hash << 5) - hash) + s.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash);
  }

  function paint(avatar) {
    if (avatar.querySelector(".rmc-avatar__img")) { return; } // photo wins
    var seed = avatar.getAttribute("data-rmc-avatar-seed");
    if (!seed) { return; }
    var idx = hashSeed(seed) % PALETTES.length;
    var pair = PALETTES[idx];
    avatar.style.setProperty("--rmc-avatar-grad-from", pair[0]);
    avatar.style.setProperty("--rmc-avatar-grad-to", pair[1]);
  }

  function paintAll(root) {
    (root || document).querySelectorAll(".rmc-avatar[data-rmc-avatar-seed]").forEach(paint);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { paintAll(); });
  } else {
    paintAll();
  }

  /* HTMX swap observer — repaint after partial updates. */
  document.addEventListener("htmx:afterSwap", function (e) { paintAll(e.target); });

  window.RMCAvatar = { paint: paint, paintAll: paintAll };
})();
