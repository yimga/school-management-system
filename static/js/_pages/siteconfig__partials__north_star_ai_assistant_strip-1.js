(function () {
  var KEY = "siteconfig__partials__north_star_ai_assistant_strip-1";
  var pageDataEl = document.getElementById("page-data-" + KEY);
  window.__RMC_PAGE_DATA__ = window.__RMC_PAGE_DATA__ || {};
  if (pageDataEl) {
    try {
      window.__RMC_PAGE_DATA__[KEY] = JSON.parse(pageDataEl.textContent || "{}");
    } catch (_e) {
      window.__RMC_PAGE_DATA__[KEY] = {};
    }
  }
  var data = window.__RMC_PAGE_DATA__[KEY] || {};
  var stripId = data["var_strip_id_escapejs"] || "";
  var apiUrl = data["var_northstar_ai_draft_url_escapejs"] || "";
  var root = document.getElementById("nsr-" + stripId);
  if (!root) return;
  var out = document.getElementById("northstar-draft-" + stripId);
  var st = document.getElementById("northstar-ai-status-" + stripId);
  var ack = document.getElementById("northstar-ack-" + stripId);
  var ins = document.getElementById("northstar-insert-" + stripId);
  var T = {
    requesting: data["trans_requesting_draft"] || "Requesting draft…",
    failed: data["trans_draft_request_failed"] || "Draft request failed.",
    ready: data["trans_draft_ready_review_before_use"] || "Draft ready — review before use.",
    network: data["trans_network_error"] || "Network error.",
    needsUrl: "AI draft endpoint not configured. Contact your operator."
  };

  function setStatus(msg) {
    if (st) st.textContent = msg || "";
  }
  function getCsrf() {
    var m = root.querySelector('input[name="csrfmiddlewaretoken"]');
    return m ? m.value : "";
  }
  function setInsertEnabled() {
    if (!ins || !ack) return;
    ins.disabled = !(ack.checked && out && out.value.trim().length > 0);
  }
  function setButtonsBusy(busy) {
    root.querySelectorAll("[data-ns-kind]").forEach(function (b) {
      b.disabled = busy;
      if (busy) {
        b.setAttribute("aria-busy", "true");
      } else {
        b.removeAttribute("aria-busy");
      }
    });
  }
  if (ack) ack.addEventListener("change", setInsertEnabled);
  if (out) out.addEventListener("input", setInsertEnabled);

  root.querySelectorAll("[data-ns-kind]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (!apiUrl) {
        setStatus(T.needsUrl);
        return;
      }
      var kind = btn.getAttribute("data-ns-kind");
      var payload = { kind: kind, context: {} };
      setStatus(T.requesting);
      if (out) out.value = "";
      setButtonsBusy(true);
      fetch(apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCsrf(),
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify(payload),
        credentials: "same-origin"
      })
        .then(function (r) {
          return r.json().then(function (j) {
            return { ok: r.ok, body: j };
          });
        })
        .then(function (res) {
          setButtonsBusy(false);
          if (!res.ok || !res.body.ok) {
            setStatus((res.body && res.body.error) || T.failed);
            return;
          }
          if (out) out.value = res.body.draft_text || "";
          setInsertEnabled();
          setStatus(T.ready);
        })
        .catch(function () {
          setButtonsBusy(false);
          setStatus(T.network);
        });
    });
  });

  if (ins) {
    ins.addEventListener("click", function () {
      var tid = ins.getAttribute("data-target-textarea");
      var ta = tid ? document.getElementById(tid) : null;
      if (ta && out) {
        ta.value = (ta.value ? ta.value + "\n\n" : "") + out.value;
        ta.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
  }
})();
