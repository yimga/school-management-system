(function(){
  var pageDataEl=document.getElementById("page-data-accounts__backend_dashboard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["accounts__backend_dashboard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  (function() {
    var tourStepsUrl = "(window.__RMC_PAGE_DATA__["accounts__backend_dashboard-1"]||{})["var_tour_steps_api_url_escapejs"]";
    var tourCompleteUrl = "(window.__RMC_PAGE_DATA__["accounts__backend_dashboard-1"]||{})["var_tour_complete_url_escapejs"]";
    var csrfToken = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1] || "";
    function getCookie(n) { var m = document.cookie.match(new RegExp("(^| )" + n + "=([^;]+)")); return m ? m[2] : ""; }
    if (!csrfToken) csrfToken = getCookie("csrftoken");
    function runTour() {
      fetch(tourStepsUrl, { credentials: "same-origin" }).then(function(r) { return r.json(); }).then(function(data) {
        var steps = (data && data.steps) ? data.steps : [];
        if (steps.length === 0) return;
        var idx = 0;
        var overlay = document.createElement("div");
        overlay.id = "backend-tour-overlay";
        overlay.setAttribute("role", "dialog");
        overlay.setAttribute("aria-modal", "true");
        overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9998;display:none;";
        var tooltip = document.createElement("div");
        tooltip.id = "backend-tour-tooltip";
        tooltip.style.cssText = "position:fixed;z-index:9999;max-width:320px;padding:1rem;background:#fff;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,0.2);display:none;";
        var titleEl = document.createElement("div");
        titleEl.className = "fw-bold mb-1";
        var btnWrap = document.createElement("div");
        btnWrap.className = "mt-2 d-flex justify-content-between gap-2";
        var skipBtn = document.createElement("button");
        skipBtn.type = "button";
        skipBtn.className = "btn btn-sm btn-outline-secondary";
        skipBtn.textContent = "(window.__RMC_PAGE_DATA__["accounts__backend_dashboard-1"]||{})["trans_skip"]";
        var nextBtn = document.createElement("button");
        nextBtn.type = "button";
        nextBtn.className = "btn btn-sm btn-primary";
        nextBtn.textContent = "(window.__RMC_PAGE_DATA__["accounts__backend_dashboard-1"]||{})["trans_next"]";
        tooltip.appendChild(titleEl);
        tooltip.appendChild(btnWrap);
        btnWrap.appendChild(skipBtn);
        btnWrap.appendChild(nextBtn);
        document.body.appendChild(overlay);
        document.body.appendChild(tooltip);
        function highlight(el) {
          if (!el) return;
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          var r = el.getBoundingClientRect();
          tooltip.style.left = (r.left + window.scrollX) + "px";
          tooltip.style.top = (r.bottom + window.scrollY + 8) + "px";
          tooltip.style.display = "block";
        }
        function showStep() {
          if (idx >= steps.length) {
            overlay.style.display = "none";
            tooltip.style.display = "none";
            fetch(tourCompleteUrl, { method: "POST", headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/x-www-form-urlencoded" }, body: "csrfmiddlewaretoken=" + encodeURIComponent(csrfToken), credentials: "same-origin" }).catch(function(){});
            return;
          }
          var step = steps[idx];
          var sel = step.selector || ("[data-tour='" + step.code + "']");
          var el = document.querySelector(sel);
          overlay.style.display = "block";
          titleEl.textContent = step.title || step.code;
          nextBtn.textContent = idx === steps.length - 1 ? "(window.__RMC_PAGE_DATA__["accounts__backend_dashboard-1"]||{})["trans_done"]" : "(window.__RMC_PAGE_DATA__["accounts__backend_dashboard-1"]||{})["trans_next_2"]";
          highlight(el);
        }
        skipBtn.addEventListener("click", function() {
          overlay.style.display = "none";
          tooltip.style.display = "none";
          fetch(tourCompleteUrl, { method: "POST", headers: { "X-CSRFToken": csrfToken, "Content-Type": "application/x-www-form-urlencoded" }, body: "csrfmiddlewaretoken=" + encodeURIComponent(csrfToken), credentials: "same-origin" }).catch(function(){});
        });
        nextBtn.addEventListener("click", function() {
          idx++;
          showStep();
        });
        overlay.addEventListener("click", function() { skipBtn.click(); });
        showStep();
      }).catch(function() {});
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", function() { setTimeout(runTour, 600); });
    else setTimeout(runTour, 600);
  })();
  
})();
