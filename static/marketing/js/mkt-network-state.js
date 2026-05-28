/**
 * Rugged engine network drop simulator (fiber → blackout).
 */
(function () {
  "use strict";

  var LABEL_ATTR = {
    fiber: "data-fiber-label",
    degraded: "data-degraded-label",
    offline: "data-offline-label",
    blackout: "data-blackout-label",
    online: "data-online-label",
  };

  function labelFor(statusEl, state) {
    if (!statusEl) return "";
    var attr = LABEL_ATTR[state] || LABEL_ATTR.fiber;
    return statusEl.getAttribute(attr) || "";
  }

  function init(root) {
    var status = root.querySelector("[data-mkt-network-status]");
    var viz = root.querySelector("[data-mkt-network-viz]");
    var fragment = root.querySelector("[data-mkt-network-fragment]");
    var buttons = root.querySelectorAll("[data-mkt-network]");
    var dropSim = root.hasAttribute("data-mkt-drop-simulator");

    function applyState(state) {
      var offline = state === "offline" || state === "blackout";
      var blackout = state === "blackout";
      var degraded = state === "degraded";
      root.classList.toggle("is-offline", offline);
      root.classList.toggle("is-blackout", blackout);
      root.classList.toggle("is-degraded", degraded);
      if (status) status.textContent = labelFor(status, state) || state;
      if (viz) viz.hidden = blackout;
      if (fragment) fragment.hidden = !blackout && !degraded;
    }

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) {
          b.classList.remove("is-active");
          b.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("is-active");
        btn.setAttribute("aria-pressed", "true");
        var state = btn.getAttribute("data-mkt-network") || "fiber";
        if (!dropSim && state !== "online" && state !== "offline") {
          state = state === "offline" ? "offline" : "fiber";
        }
        applyState(state);
      });
    });

    var active = root.querySelector("[data-mkt-network].is-active");
    applyState(
      active ? active.getAttribute("data-mkt-network") || "fiber" : dropSim ? "fiber" : "online"
    );
  }

  document.querySelectorAll("[data-mkt-network-state]").forEach(init);
})();
