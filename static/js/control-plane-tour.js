/**
 * Control-plane page tours (BR-13): trust center, migration CSV diff, governed query.
 * Context from URL path; steps from siteconfig:tour_steps_api.
 */
(function () {
  function tourContext() {
    var p = window.location.pathname || "";
    if (/\/super\/trust\/?$/.test(p)) return "super_trust";
    if (p.indexOf("/super/migration/csv-diff") !== -1) return "super_migration";
    if (p.indexOf("/super/tools/governed-query") !== -1) return "super_governed";
    return null;
  }

  function getTourApiBase() {
    var s = document.querySelector("script[data-tour-api]");
    return (s && s.getAttribute("data-tour-api")) || "";
  }

  function runTour(steps) {
    if (!steps || !steps.length) return;
    var idx = 0;
    var overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.style.cssText =
      "position:fixed;inset:0;background:rgba(0,0,0,0.55);z-index:10040;display:block;";
    var tooltip = document.createElement("div");
    tooltip.style.cssText =
      "position:fixed;z-index:10041;max-width:min(92vw,340px);padding:1rem;background:#fff;color:#111;border-radius:10px;box-shadow:0 12px 40px rgba(0,0,0,0.25);";
    var titleEl = document.createElement("div");
    titleEl.className = "fw-bold mb-2";
    var btnWrap = document.createElement("div");
    btnWrap.className = "mt-2 d-flex justify-content-between gap-2 flex-wrap";
    var skipBtn = document.createElement("button");
    skipBtn.type = "button";
    skipBtn.className = "btn btn-sm btn-outline-secondary";
    skipBtn.textContent = "Skip";
    var nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "btn btn-sm btn-primary";
    nextBtn.textContent = "Next";
    tooltip.appendChild(titleEl);
    tooltip.appendChild(btnWrap);
    btnWrap.appendChild(skipBtn);
    btnWrap.appendChild(nextBtn);
    document.body.appendChild(overlay);
    document.body.appendChild(tooltip);

    function placeTooltip(el) {
      if (!el) {
        tooltip.style.left = "50%";
        tooltip.style.top = "30%";
        tooltip.style.transform = "translate(-50%,0)";
        return;
      }
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      var r = el.getBoundingClientRect();
      var left = Math.min(
        window.innerWidth - 24 - tooltip.offsetWidth,
        Math.max(12, r.left)
      );
      var top = r.bottom + 12 + window.scrollY;
      if (top + 120 > window.innerHeight + window.scrollY) {
        top = r.top + window.scrollY - tooltip.offsetHeight - 12;
      }
      tooltip.style.left = left + "px";
      tooltip.style.top = Math.max(12, top) + "px";
      tooltip.style.transform = "none";
    }

    function close() {
      overlay.remove();
      tooltip.remove();
    }

    function showStep() {
      if (idx >= steps.length) {
        close();
        return;
      }
      var step = steps[idx];
      var sel = step.selector || "[data-tour='" + step.code + "']";
      var el = document.querySelector(sel);
      titleEl.textContent = step.title || step.code;
      nextBtn.textContent = idx === steps.length - 1 ? "Done" : "Next";
      placeTooltip(el);
    }

    skipBtn.addEventListener("click", close);
    nextBtn.addEventListener("click", function () {
      idx += 1;
      showStep();
    });
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });
    showStep();
  }

  function init() {
    var ctx = tourContext();
    if (!ctx) return;
    var api = getTourApiBase();
    if (!api) return;
    var fab = document.getElementById("cpTourFab");
    var btn = document.getElementById("cpTourStartBtn");
    if (!fab || !btn) return;
    fab.classList.remove("d-none");
    btn.addEventListener("click", function () {
      var url = api + (api.indexOf("?") >= 0 ? "&" : "?") + "context=" + encodeURIComponent(ctx);
      fetch(url, { credentials: "same-origin" })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          var steps = (data && data.steps) || [];
          if (steps.length) runTour(steps);
        })
        .catch(function () {});
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
