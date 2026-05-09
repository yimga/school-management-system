(function(){
  var pageDataEl=document.getElementById("page-data-siteconfig__partials__north_star_ai_assistant_strip-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["siteconfig__partials__north_star_ai_assistant_strip-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
  (function() {
    var stripId = "(window.__RMC_PAGE_DATA__["siteconfig__partials__north_star_ai_assistant_strip-1"]||{})["var_strip_id_escapejs"]";
    var apiUrl = "(window.__RMC_PAGE_DATA__["siteconfig__partials__north_star_ai_assistant_strip-1"]||{})["var_northstar_ai_draft_url_escapejs"]";
    var root = document.getElementById("nsr-" + stripId);
    if (!root || !apiUrl) return;
    var out = document.getElementById("northstar-draft-" + stripId);
    var st = document.getElementById("northstar-ai-status-" + stripId);
    var ack = document.getElementById("northstar-ack-" + stripId);
    var ins = document.getElementById("northstar-insert-" + stripId);
    function setStatus(msg) { if (st) st.textContent = msg || ""; }
    function getCsrf() {
      var m = document.querySelector('#nsr-' + stripId + ' input[name="csrfmiddlewaretoken"]');
      return m ? m.value : "";
    }
    function setInsertEnabled() {
      if (!ins || !ack) return;
      ins.disabled = !(ack.checked && out && out.value.trim().length > 0);
    }
    if (ack) ack.addEventListener("change", setInsertEnabled);
    if (out) out.addEventListener("input", setInsertEnabled);
    root.querySelectorAll("[data-ns-kind]").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var kind = btn.getAttribute("data-ns-kind");
        var payload = { kind: kind, context: {} };
        setStatus("{% filter escapejs %}(window.__RMC_PAGE_DATA__["siteconfig__partials__north_star_ai_assistant_strip-1"]||{})["trans_requesting_draft"]{% endfilter %}");
        if (out) out.value = "";
        fetch(apiUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCsrf(),
            "X-Requested-With": "XMLHttpRequest"
          },
          body: JSON.stringify(payload),
          credentials: "same-origin"
        }).then(function(r) { return r.json().then(function(j) { return { ok: r.ok, body: j }; }); })
        .then(function(res) {
          if (!res.ok || !res.body.ok) {
            setStatus(res.body.error || "{% filter escapejs %}(window.__RMC_PAGE_DATA__["siteconfig__partials__north_star_ai_assistant_strip-1"]||{})["trans_draft_request_failed"]{% endfilter %}");
            return;
          }
          if (out) out.value = res.body.draft_text || "";
          setInsertEnabled();
          setStatus("{% filter escapejs %}(window.__RMC_PAGE_DATA__["siteconfig__partials__north_star_ai_assistant_strip-1"]||{})["trans_draft_ready_review_before_use"]{% endfilter %}");
        }).catch(function() {
          setStatus("{% filter escapejs %}(window.__RMC_PAGE_DATA__["siteconfig__partials__north_star_ai_assistant_strip-1"]||{})["trans_network_error"]{% endfilter %}");
        });
      });
    });
    if (ins) {
      ins.addEventListener("click", function() {
        var tid = ins.getAttribute("data-target-textarea");
        var ta = tid ? document.getElementById(tid) : null;
        if (ta && out) {
          ta.value = (ta.value ? ta.value + "\n\n" : "") + out.value;
          ta.dispatchEvent(new Event("input", { bubbles: true }));
        }
      });
    }
  })();
  
})();
