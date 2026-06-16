/* Operator (/super/) Remote Support console — herd-safe session poller.
 *
 * Polls super:remote_support_sessions (sessions.json, GET — read-only list) on a
 * visibility-gated loop with exponential backoff + a circuit breaker (the
 * self-inflicted thundering-herd lesson from the /super/ 502 incident), renders
 * the open-session rows, and wires per-row Accept (POST accept) and End (POST end,
 * with an optional summary prompt). Endpoint URLs + the placeholder UUID are read
 * from #rmc-super-remote-support-config (reverse()'d in Django) so nothing
 * hardcodes a mount path. CSRF token is read from the cookie. Dependency-free.
 *
 * Tenant isolation is enforced server-side: the accept/end views call
 * operator_can_remote_support(user, session.school) and return 403 when the
 * operator may not act on that tenant. This client never assumes it can.
 */
(function () {
  "use strict";

  var cfgEl = document.getElementById("rmc-super-remote-support-config");
  if (!cfgEl) return;

  var CFG;
  try {
    CFG = JSON.parse(cfgEl.textContent || "{}");
  } catch (e) {
    return;
  }
  var L = CFG.labels || {};
  var PLACEHOLDER = CFG.placeholder || "00000000-0000-0000-0000-000000000000";

  var rows = document.querySelector("[data-rmc-remote-support-rows]");
  var statusEl = document.querySelector("[data-rmc-remote-support-status]");
  if (!rows) return;

  function csrf() {
    // Manager host isolates the CSRF cookie under rmc_manager_csrftoken and blanks
    // the plain csrftoken cookie (config/settings.py MANAGER_CSRF_COOKIE_NAME). This
    // console mounts on the manager host, so match the platform POST-helper convention
    // (rmc-copilot-rail.js): prefer a csrf-token meta tag, then either cookie name.
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content && meta.content !== "NOTPROVIDED") {
      return meta.content;
    }
    var m = document.cookie.match(
      /(?:^|;\s*)(?:csrftoken|rmc_manager_csrftoken)=([^;]+)/
    );
    return m ? decodeURIComponent(m[1]) : "";
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "";
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrf(),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body || "",
      credentials: "same-origin",
    });
  }

  function expand(template, sid) {
    return String(template || "").replace(PLACEHOLDER, encodeURIComponent(sid));
  }

  /* --- rendering ---------------------------------------------------------- */
  function clearRows() {
    while (rows.firstChild) rows.removeChild(rows.firstChild);
  }

  function renderEmpty() {
    clearRows();
    var tr = document.createElement("tr");
    tr.setAttribute("data-rmc-remote-support-empty-row", "");
    var td = document.createElement("td");
    td.setAttribute("colspan", "6");
    td.className = "text-secondary";
    td.textContent = L.empty || "No open remote-support sessions.";
    tr.appendChild(td);
    rows.appendChild(tr);
  }

  function cell(text, className) {
    var td = document.createElement("td");
    if (className) td.className = className;
    td.textContent = text == null ? "" : String(text);
    return td;
  }

  function actionButton(label, variant, attr, sid) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-sm " + variant;
    btn.textContent = label;
    btn.setAttribute(attr, "");
    btn.setAttribute("data-session-id", sid);
    return btn;
  }

  function renderSessions(sessions) {
    if (!sessions || !sessions.length) {
      renderEmpty();
      return;
    }
    clearRows();
    sessions.forEach(function (s) {
      var tr = document.createElement("tr");
      tr.setAttribute("data-rmc-remote-support-row", "");
      tr.setAttribute("data-session-id", s.id);

      // School column: id only (sessions.json never exposes tenant names — keep it that way).
      var schoolTd = document.createElement("td");
      var code = document.createElement("code");
      code.className = "small";
      code.textContent = s.school_id || "—";
      schoolTd.appendChild(code);
      tr.appendChild(schoolTd);

      tr.appendChild(cell(s.status));
      tr.appendChild(cell(s.channel));
      tr.appendChild(cell(s.reason || "—"));

      // Consent indicator.
      var consentTd = document.createElement("td");
      var pill = document.createElement("span");
      if (s.needs_consent) {
        pill.className = "badge text-bg-warning";
        pill.textContent = L.needs_consent || "Awaiting consent";
      } else {
        pill.className = "badge text-bg-success";
        pill.textContent = L.consent_ok || "Ready";
      }
      consentTd.appendChild(pill);
      tr.appendChild(consentTd);

      // Actions.
      var actionsTd = document.createElement("td");
      var group = document.createElement("div");
      group.className = "d-flex flex-wrap gap-1 justify-content-end";
      group.appendChild(
        actionButton(
          L.accept || "Accept",
          "btn-outline-primary",
          "data-rmc-remote-support-accept",
          s.id
        )
      );
      group.appendChild(
        actionButton(
          L.end || "End",
          "btn-outline-danger",
          "data-rmc-remote-support-end",
          s.id
        )
      );
      actionsTd.appendChild(group);
      tr.appendChild(actionsTd);

      rows.appendChild(tr);
    });
  }

  /* --- actions ------------------------------------------------------------ */
  function disableRow(btn) {
    var tr = btn.closest("tr");
    if (!tr) return;
    var buttons = tr.querySelectorAll("button");
    for (var i = 0; i < buttons.length; i++) buttons[i].disabled = true;
  }

  document.addEventListener("click", function (e) {
    var accept = e.target.closest("[data-rmc-remote-support-accept]");
    if (accept) {
      var sid = accept.getAttribute("data-session-id");
      disableRow(accept);
      setStatus(L.accepting || "");
      post(expand(CFG.accept_url_template, sid))
        .then(function () {
          fetchNow();
        })
        .catch(function () {
          fetchNow();
        });
      return;
    }
    var end = e.target.closest("[data-rmc-remote-support-end]");
    if (end) {
      var esid = end.getAttribute("data-session-id");
      var summary = "";
      try {
        summary = window.prompt(L.end_prompt || "Optional summary:", "") || "";
      } catch (err) {
        summary = "";
      }
      disableRow(end);
      setStatus(L.ending || "");
      post(
        expand(CFG.end_url_template, esid),
        "summary=" + encodeURIComponent(summary)
      )
        .then(function () {
          fetchNow();
        })
        .catch(function () {
          fetchNow();
        });
      return;
    }
    var refresh = e.target.closest("[data-rmc-remote-support-refresh]");
    if (refresh) {
      fetchNow();
    }
  });

  /* --- herd-safe poll loop ------------------------------------------------ */
  var BASE_MS = 15000;
  var MAX_MS = 300000;
  var MAX_FAILS = 5;
  var fails = 0;
  var stopped = false;
  var timer = null;
  var inFlight = false;

  function schedule(ms) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(tick, ms);
  }

  function load() {
    if (inFlight) return Promise.resolve();
    inFlight = true;
    return fetch(CFG.sessions_url, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (r) {
        if (!r || !r.ok) throw new Error("bad_status");
        return r.json();
      })
      .then(function (data) {
        renderSessions((data && data.sessions) || []);
        setStatus(L.loaded || "");
        fails = 0;
      })
      .catch(function () {
        fails += 1;
        setStatus(L.error || "");
        throw new Error("load_failed");
      })
      .then(
        function () {
          inFlight = false;
        },
        function (err) {
          inFlight = false;
          throw err;
        }
      );
  }

  function tick() {
    if (stopped || document.visibilityState !== "visible") return;
    load()
      .then(function () {
        schedule(BASE_MS);
      })
      .catch(function () {
        if (fails >= MAX_FAILS) {
          stopped = true; // circuit breaker — stop hammering a down server
          return;
        }
        schedule(Math.min(MAX_MS, BASE_MS * Math.pow(2, fails)));
      });
  }

  function fetchNow() {
    // Manual / post-action refresh: re-arm the breaker and poll immediately.
    stopped = false;
    fails = 0;
    if (timer) clearTimeout(timer);
    tick();
  }

  if (document.visibilityState === "visible") {
    schedule(0);
  }
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible" && !stopped) {
      schedule(0);
    }
  });
})();
