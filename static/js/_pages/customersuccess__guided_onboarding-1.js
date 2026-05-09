(function(){
  var pageDataEl=document.getElementById("page-data-customersuccess__guided_onboarding-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["customersuccess__guided_onboarding-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  (function () {
    var root = document.getElementById("setup-studio-ai-coach");
    if (!root || !root.dataset.coachUrl) return;
    fetch(root.dataset.coachUrl, { credentials: "same-origin", headers: { Accept: "application/json" } })
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
          src.textContent = d.source === "ai" ? "(window.__RMC_PAGE_DATA__["customersuccess__guided_onboarding-1"]||{})["trans_powered_by_ai_gateway"]" :
            (d.source === "rules+ai" ? "(window.__RMC_PAGE_DATA__["customersuccess__guided_onboarding-1"]||{})["trans_ai_enhanced_suggestions"]" : "(window.__RMC_PAGE_DATA__["customersuccess__guided_onboarding-1"]||{})["trans_based_on_your_setup_progress"]");
        }
        root.hidden = false;
      })
      .catch(function () {});
  })();
  
})();
