(function () {
  var KEY = "schools__super_global_ai_version_progress-1";
  var pageDataEl = document.getElementById("page-data-" + KEY);
  window.__RMC_PAGE_DATA__ = window.__RMC_PAGE_DATA__ || {};
  if (pageDataEl) {
    try {
      window.__RMC_PAGE_DATA__[KEY] = JSON.parse(pageDataEl.textContent || "{}");
    } catch (_e) {
      window.__RMC_PAGE_DATA__[KEY] = {};
    }
  }
  var DATA = window.__RMC_PAGE_DATA__[KEY] || {};
  var runId = DATA["var_run_id_escapejs"] || "";
  var progressUrl = "?json=1" + (runId ? "&run_id=" + encodeURIComponent(runId) : "");

  function poll() {
    fetch(window.location.pathname + progressUrl)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var total = data.regions_total || 0;
        var done = data.regions_done !== undefined ? data.regions_done : 0;
        var status = data.status || "unknown";
        var el = document.getElementById("progress-text");
        if (el) el.textContent = status + " — " + done + " / " + total + " regions.";
        if (status !== "done" && status !== "error") setTimeout(poll, 2000);
      })
      .catch(function () {
        var el = document.getElementById("progress-text");
        if (el) el.textContent = "Error loading progress.";
      });
  }
  poll();
})();
