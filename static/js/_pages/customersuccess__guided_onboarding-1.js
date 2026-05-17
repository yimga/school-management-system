(function () {
  var KEY = "customersuccess__guided_onboarding-1";
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
  var T = {
    aiPowered: DATA["trans_powered_by_ai_gateway"] || "Powered by AI gateway",
    aiEnhanced: DATA["trans_ai_enhanced_suggestions"] || "AI-enhanced suggestions",
    progressBased: DATA["trans_based_on_your_setup_progress"] || "Based on your setup progress",
  };

  var root = document.getElementById("setup-studio-ai-coach");
  if (!root || !root.dataset.coachUrl) return;
  fetch(root.dataset.coachUrl, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (!d || !d.ok) return;
      var msg = root.querySelector("[data-coach-message]");
      if (msg && d.coach_message) msg.textContent = d.coach_message;
      var actions = root.querySelector("[data-coach-actions]");
      if (actions && d.quick_actions && d.quick_actions.length) {
        actions.innerHTML = "";
        d.quick_actions.forEach(function (a) {
          if (!a.url || !a.label) return;
          var link = document.createElement("a");
          link.href = a.url;
          link.className = "btn btn-primary btn-sm me-2 mb-2";
          link.textContent = a.label;
          actions.appendChild(link);
        });
      }
      var src = root.querySelector("[data-coach-source]");
      if (src) {
        if (d.source === "ai") {
          src.textContent = T.aiPowered;
        } else if (d.source === "rules+ai") {
          src.textContent = T.aiEnhanced;
        } else {
          src.textContent = T.progressBased;
        }
      }
      root.hidden = false;
    })
    .catch(function () {});
})();
