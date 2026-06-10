/**

 * Tenant dashboard operational health widget — SSE heartbeat with JSON poll fallback.

 */

(function () {

  "use strict";



  var DEFAULT_POLL_MS = 15000;



  function tierClass(tier) {

    if (tier === "down") return "rmc-tenant-health--down";

    if (tier === "degraded") return "rmc-tenant-health--degraded";

    return "rmc-tenant-health--up";

  }



  function pillToneClass(tone) {

    if (tone === "danger") return "table-status-chip--danger";

    if (tone === "warning") return "table-status-chip--warning";

    if (tone === "success") return "table-status-chip--success";

    return "table-status-chip--muted";

  }



  function applyPayload(root, payload) {

    if (!payload) return;

    var revision = payload.revision || "";

    if (revision && root.getAttribute("data-rmc-tenant-health-revision") === revision) return;

    root.setAttribute("data-rmc-tenant-health-revision", revision);



    root.classList.remove("rmc-tenant-health--up", "rmc-tenant-health--degraded", "rmc-tenant-health--down");

    root.classList.add(tierClass(payload.tier || "up"));



    var labelEl = root.querySelector("[data-rmc-tenant-health-label]");

    if (labelEl) labelEl.textContent = payload.label || "—";



    var signalsEl = root.querySelector("[data-rmc-tenant-health-signals]");

    if (signalsEl && payload.signals) {

      var html = "";

      for (var i = 0; i < payload.signals.length; i++) {

        var sig = payload.signals[i];

        html +=

          '<span class="table-status-chip ' +

          pillToneClass(sig.tone) +

          ' me-1 mb-1">' +

          String(sig.label || "") +

          "</span>";

      }

      signalsEl.innerHTML = html;

    }



    var stamp = root.querySelector("[data-rmc-tenant-health-refreshed]");

    if (stamp) {

      try {

        stamp.textContent = new Date().toLocaleTimeString();

      } catch (_) { /* noop */ }

    }

  }



  function buildEndpoint(root) {

    var base = root.getAttribute("data-rmc-tenant-health-endpoint") || "";

    if (!base) return "";

    var surface = root.getAttribute("data-rmc-tenant-health-surface") || "admin";

    var sep = base.indexOf("?") >= 0 ? "&" : "?";

    return base + sep + "surface=" + encodeURIComponent(surface);

  }



  function buildStreamEndpoint(root) {

    var base = root.getAttribute("data-rmc-tenant-health-stream-endpoint") || "";

    if (!base) return "";

    var surface = root.getAttribute("data-rmc-tenant-health-surface") || "admin";

    var sep = base.indexOf("?") >= 0 ? "&" : "?";

    return base + sep + "surface=" + encodeURIComponent(surface);

  }



  function pollOnce(root, intervalRef) {

    var url = buildEndpoint(root);

    if (!url) return;

    fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })

      .then(function (r) {

        if (!r.ok) throw new Error("status_" + r.status);

        return r.json();

      })

      .then(function (payload) {

        if (payload && payload.poll_interval_seconds && intervalRef) {

          intervalRef.ms = Math.max(5000, Number(payload.poll_interval_seconds) * 1000);

        }

        applyPayload(root, payload);

      })

      .catch(function () { /* SSR snapshot remains */ });

  }



  function bootRoot(root) {

    var intervalRef = { ms: DEFAULT_POLL_MS, handle: null };

    var lastSseRevision = "";



    pollOnce(root, intervalRef);

    intervalRef.handle = window.setInterval(function () {

      pollOnce(root, intervalRef);

    }, intervalRef.ms);



    if (typeof EventSource === "undefined") return;



    var sseUrl = buildStreamEndpoint(root);

    if (!sseUrl) return;



    var source = new EventSource(sseUrl, { withCredentials: true });



    source.onmessage = function (event) {

      try {

        var payload = JSON.parse(event.data || "{}");

        if (payload.revision && payload.revision === lastSseRevision) return;

        lastSseRevision = payload.revision || "";

        applyPayload(root, payload);

        pollOnce(root, intervalRef);

      } catch (_) { /* noop */ }

    };



    source.onerror = function () {

      /* poll fallback continues */

    };

  }



  function boot() {

    var roots = document.querySelectorAll("[data-rmc-tenant-health-live='1']");

    for (var i = 0; i < roots.length; i++) bootRoot(roots[i]);

  }



  if (document.readyState === "loading") {

    document.addEventListener("DOMContentLoaded", boot);

  } else {

    boot();

  }

})();

