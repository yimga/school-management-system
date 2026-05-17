/**
 * Bootstrap popovers for rmc_info_tag partial; optional API hydration.
 */
(function () {
  function infoApiBase() {
    var el = document.querySelector("script[data-tour-info-api]");
    return (el && el.getAttribute("data-tour-info-api")) || "";
  }

  function hydrateFromApi(btn) {
    var entity = btn.getAttribute("data-rmc-info-entity");
    var field = btn.getAttribute("data-rmc-info-field");
    var feature = btn.getAttribute("data-rmc-info-feature");
    if (!entity && !field && !feature) return;
    var base = infoApiBase();
    if (!base) return;
    var qs = new URLSearchParams();
    if (entity) qs.set("entity", entity);
    if (field) qs.set("field", field);
    if (feature) qs.set("feature", feature);
    fetch(base + "?" + qs.toString(), { credentials: "same-origin" })
      .then(function (r) {
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (!data || !data.ok) return;
        if (data.title) btn.setAttribute("data-bs-title", data.title);
        if (data.body) btn.setAttribute("data-bs-content", data.body);
        var inst = window.bootstrap && bootstrap.Popover.getInstance(btn);
        if (inst) inst.dispose();
        if (window.bootstrap && bootstrap.Popover) {
          new bootstrap.Popover(btn, { container: "body", sanitize: true });
        }
      })
      .catch(function () {});
  }

  function init() {
    if (!window.bootstrap || !bootstrap.Popover) return;
    document.querySelectorAll(".rmc-info-tag [data-bs-toggle='popover']").forEach(function (el) {
      if (bootstrap.Popover.getInstance(el)) return;
      new bootstrap.Popover(el, { container: "body", sanitize: true });
      if (el.hasAttribute("data-rmc-info-entity") || el.hasAttribute("data-rmc-info-feature")) {
        hydrateFromApi(el);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
