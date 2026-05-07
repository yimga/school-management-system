/**
 * Platform behavior instrumentation (Phase 4) + click persistence (measurement contract).
 *
 * Templates: data-task, data-task-step, data-action on actionable controls.
 * Optional: window.__RMC_CLICK_INGEST + window.__RMC_CLICK_PHASE (baseline|current)
 * set by portal_base when tenant + authenticated.
 *
 * Emits CustomEvent "rmcTaskTelemetry" for bridges; POSTs click rows when ingest URL present.
 */
(function () {
  if (typeof window === "undefined" || !window.document) return;

  var SESSION_KEY = "rmc.click.run.ids.v1";

  function emit(payload) {
    try {
      window.dispatchEvent(new CustomEvent("rmcTaskTelemetry", { detail: payload }));
    } catch (_e) {}
    if (window.console && window.console.debug) {
      console.debug("[rmc-task]", payload);
    }
  }

  function getCookie(name) {
    var cookies = document.cookie ? document.cookie.split(";") : [];
    for (var i = 0; i < cookies.length; i++) {
      var c = cookies[i].trim();
      if (c.indexOf(name + "=") === 0) return decodeURIComponent(c.substring(name.length + 1));
    }
    return "";
  }

  function sessionRunIdForTask(taskCode) {
    if (!taskCode) return "";
    try {
      var raw = sessionStorage.getItem(SESSION_KEY);
      var map = raw ? JSON.parse(raw) : {};
      if (!map[taskCode]) {
        map[taskCode] =
          window.crypto && typeof window.crypto.randomUUID === "function"
            ? window.crypto.randomUUID()
            : "run-" + Date.now() + "-" + Math.random().toString(36).slice(2, 9);
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(map));
      }
      return map[taskCode];
    } catch (_e) {
      return "run-fallback-" + Date.now();
    }
  }

  function phaseLabel() {
    var p = window.__RMC_CLICK_PHASE || "";
    if (!p && document.body && document.body.getAttribute) {
      p = document.body.getAttribute("data-click-measurement-phase") || "";
    }
    p = (p || "current").toLowerCase();
    return p === "baseline" ? "baseline" : "current";
  }

  function postIngest(body) {
    var url = window.__RMC_CLICK_INGEST;
    if (!url) return;
    try {
      fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken"),
        },
        body: JSON.stringify(body),
        keepalive: true,
      }).catch(function () {});
    } catch (_e) {}
  }

  document.addEventListener(
    "click",
    function (ev) {
      var el = ev.target && ev.target.closest ? ev.target.closest("[data-action], [data-task-step], [data-task]") : null;
      if (!el) return;
      var action = el.getAttribute("data-action") || "";
      var step = el.getAttribute("data-task-step") || "";
      var taskFromEl = el.getAttribute("data-task") || "";
      var taskWrap = el.closest ? el.closest("[data-task]") : null;
      var taskCode = taskFromEl || (taskWrap ? taskWrap.getAttribute("data-task") : "") || "";
      if (!action && !step && !taskCode) return;

      var path = window.location && window.location.pathname ? window.location.pathname : "";
      var sessionId = sessionRunIdForTask(taskCode);

      emit({
        kind: "click",
        action: action,
        task_step: step,
        task_code: taskCode,
        path: path,
        ts: Date.now(),
      });

      if (taskCode && sessionId) {
        postIngest({
          kind: "click",
          task_code: taskCode,
          task_step: step,
          action: action,
          session_run_id: sessionId,
          phase: phaseLabel(),
          path: path,
        });
      }

      var aiRec = el.getAttribute("data-ai-rec-key") || "";
      if (aiRec && el.tagName === "A") {
        var href = el.getAttribute("href") || "";
        try {
          var u = new URL(href, window.location.origin);
          sessionStorage.setItem(
            "rmc_ai_pending_complete",
            JSON.stringify({
              task_code: taskCode || "ai:" + aiRec,
              path: u.pathname || "",
              ts: Date.now(),
            })
          );
        } catch (_e2) {}
      }
    },
    true,
  );

  function onDomReadyAiHooks() {
    try {
      var raw = sessionStorage.getItem("rmc_ai_pending_complete");
      if (raw) {
        var o = JSON.parse(raw);
        var path = window.location.pathname || "";
        if (o && o.path && path === o.path) {
          var tc = o.task_code || "";
          var sid = sessionRunIdForTask(tc);
          emit({ kind: "ai_task_completed", task_code: tc, path: path, ts: Date.now() });
          if (window.rmcClickTaskBoundary) {
            window.rmcClickTaskBoundary("task_complete", tc, {});
          }
          sessionStorage.removeItem("rmc_ai_pending_complete");
        }
      }
    } catch (_e) {}

    if (!window.IntersectionObserver) return;
    var seen = {};
    var obs = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          var chip = en.target;
          var key = chip.getAttribute("data-ai-rec-key") || "";
          if (!key || seen[key]) return;
          seen[key] = true;
          var tc = chip.getAttribute("data-task") || "ai:" + key;
          var sid = sessionRunIdForTask(tc);
          emit({ kind: "ai_suggestion_shown", task_code: tc, ts: Date.now() });
        });
      },
      { root: null, threshold: 0.15 }
    );
    document.querySelectorAll("[data-ai-rec-key]").forEach(function (el) {
      obs.observe(el);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", onDomReadyAiHooks);
  } else {
    onDomReadyAiHooks();
  }

  /** One local emit per full page load; persisted click rows require task-bound events. */
  function emitScreenTransition() {
    var path = window.location && window.location.pathname ? window.location.pathname : "";
    emit({ kind: "screen_transition", path: path, ts: Date.now() });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", emitScreenTransition);
  } else {
    emitScreenTransition();
  }

  /**
   * Workflow boundaries (call from step templates when a named workflow starts or completes).
   * Completing may reset the session id for that task in sessionStorage (next run fresh).
   */
  window.rmcClickTaskBoundary = function (kind, taskCode, options) {
    options = options || {};
    if (!taskCode || (kind !== "task_start" && kind !== "task_complete")) return;
    var sessionId = sessionRunIdForTask(taskCode);
    postIngest({
      kind: kind,
      task_code: taskCode,
      session_run_id: sessionId,
      phase: phaseLabel(),
      path: window.location.pathname || "",
      task_step: options.step || "",
      action: options.action || "",
      screen_token: options.screen_token || "",
      extra: options.extra || {},
    });
    emit({ kind: kind, task_code: taskCode, session_run_id: sessionId, ts: Date.now() });
    if (kind === "task_complete") {
      try {
        var raw = sessionStorage.getItem(SESSION_KEY);
        var map = raw ? JSON.parse(raw) : {};
        delete map[taskCode];
        sessionStorage.setItem(SESSION_KEY, JSON.stringify(map));
      } catch (_e) {}
    }
  };
})();
