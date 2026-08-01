/**
 * RunMyCampus shared guided tour (tenant backend, Studio, finance, control plane).
 */
(function (global) {
  "use strict";

  var PAGE_SLUG_TO_CONTEXT = {
    "studio-os": "studio_os",
    "finance-invoices": "finance_invoices",
    "admissions-queue": "admissions_queue",
    "teacher-gradebook": "teacher_gradebook",
    "notifications-inbox": "notifications_inbox",
    "teacher-portal": "teacher_portal",
    "parent-portal": "parent_portal",
    "student-portal": "student_portal",
  };

  var MARKETING_SLUG_TO_CONTEXT = {
    marketing: "marketing_home",
    "resources-product-tour": "marketing_product_tour",
  };

  var activeRun = null;

  function readJsonScript(id) {
    var el = document.getElementById(id);
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}");
    } catch (_e) {
      return {};
    }
  }

  function getI18n() {
    return readJsonScript("rmc-tour-i18n");
  }

  function getBootScript() {
    return document.querySelector("script[data-tour-steps-api]");
  }

  function apiBase() {
    var s = getBootScript();
    return (s && s.getAttribute("data-tour-steps-api")) || "";
  }

  function analyticsBase() {
    var s = getBootScript();
    return (s && s.getAttribute("data-tour-analytics-api")) || "";
  }

  function getCsrf() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    var m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function track(event, context) {
    var url = analyticsBase();
    if (!url) return;
    var body = new URLSearchParams();
    body.set("event", event);
    if (context) body.set("context", context);
    var csrf = getCsrf();
    if (csrf) body.set("csrfmiddlewaretoken", csrf);
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": csrf,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    }).catch(function () {});
  }

  function stepsUrl(context) {
    var base = apiBase();
    if (!base) return "";
    var sep = base.indexOf("?") >= 0 ? "&" : "?";
    return base + sep + "context=" + encodeURIComponent(context);
  }

  function fetchSteps(context) {
    var url = stepsUrl(context);
    if (!url) return Promise.resolve([]);
    return fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        return (data && data.steps) || [];
      })
      .catch(function () {
        return [];
      });
  }

  function markComplete(completeUrl) {
    if (!completeUrl) return;
    var csrf = getCsrf();
    fetch(completeUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrf,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: "csrfmiddlewaretoken=" + encodeURIComponent(csrf),
      credentials: "same-origin",
    }).catch(function () {});
  }

  function formatStepOf(i18n, current, total) {
    var tpl = i18n.step_of || "Step %(current)s of %(total)s";
    return tpl
      .replace("%(current)s", String(current))
      .replace("%(total)s", String(total));
  }

  function runTour(steps, options) {
    options = options || {};
    if (!steps || !steps.length) return;
    if (activeRun && activeRun.close) activeRun.close();

    var i18n = getI18n();
    var context = options.context || "";
    var idx = 0;
    var overlay = document.createElement("div");
    overlay.className = "rmc-tour-overlay";
    overlay.setAttribute("role", "presentation");

    var spotlight = document.createElement("div");
    spotlight.className = "rmc-tour-spotlight";
    spotlight.setAttribute("aria-hidden", "true");

    var tooltip = document.createElement("div");
    tooltip.className = "rmc-tour-tooltip";
    tooltip.setAttribute("role", "dialog");
    tooltip.setAttribute("aria-modal", "true");
    tooltip.setAttribute("aria-live", "polite");

    var stepLabel = document.createElement("div");
    stepLabel.className = "small text-muted mb-1";
    var titleEl = document.createElement("div");
    titleEl.className = "rmc-tour-tooltip__title";
    var bodyEl = document.createElement("div");
    bodyEl.className = "rmc-tour-tooltip__body";
    var missingEl = document.createElement("div");
    missingEl.className = "rmc-tour-tooltip__missing";
    missingEl.hidden = true;

    var btnWrap = document.createElement("div");
    btnWrap.className = "d-flex justify-content-between gap-2 flex-wrap";
    var skipBtn = document.createElement("button");
    skipBtn.type = "button";
    skipBtn.className = "btn btn-sm btn-outline-secondary";
    skipBtn.textContent = i18n.skip || "Skip";
    var nextBtn = document.createElement("button");
    nextBtn.type = "button";
    nextBtn.className = "btn btn-sm btn-primary";
    nextBtn.textContent = i18n.next || "Next";

    tooltip.appendChild(stepLabel);
    tooltip.appendChild(titleEl);
    tooltip.appendChild(bodyEl);
    tooltip.appendChild(missingEl);
    tooltip.appendChild(btnWrap);
    btnWrap.appendChild(skipBtn);
    btnWrap.appendChild(nextBtn);
    document.body.appendChild(overlay);
    document.body.appendChild(spotlight);
    document.body.appendChild(tooltip);

    var highlightedEl = null;
    var lastFocus = document.activeElement;

    function clearHighlight() {
      if (highlightedEl) {
        highlightedEl.classList.remove("rmc-tour-highlight-target");
        highlightedEl = null;
      }
      spotlight.style.width = "0";
      spotlight.style.height = "0";
    }

    function placeSpotlight(el) {
      if (!el) {
        clearHighlight();
        return;
      }
      el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      highlightedEl = el;
      el.classList.add("rmc-tour-highlight-target");
      var pad = 6;
      var r = el.getBoundingClientRect();
      spotlight.style.left = Math.max(0, r.left - pad) + "px";
      spotlight.style.top = Math.max(0, r.top - pad) + "px";
      spotlight.style.width = r.width + pad * 2 + "px";
      spotlight.style.height = r.height + pad * 2 + "px";
    }

    function placeTooltip(el) {
      var rect = tooltip.getBoundingClientRect();
      var vw = window.innerWidth;
      var vh = window.innerHeight;
      var left;
      var top;
      if (el) {
        var r = el.getBoundingClientRect();
        left = Math.min(vw - rect.width - 12, Math.max(12, r.left));
        top = r.bottom + 12;
        if (top + rect.height > vh - 12) {
          top = Math.max(12, r.top - rect.height - 12);
        }
      } else {
        left = (vw - rect.width) / 2;
        top = vh * 0.28;
      }
      tooltip.style.left = left + "px";
      tooltip.style.top = top + "px";
    }

    function finish(reason) {
      if (reason === "complete") {
        track("complete", context);
        if (options.completeUrl) markComplete(options.completeUrl);
      } else if (reason === "skip") {
        track("skip", context);
        if (options.completeUrl && options.markCompleteOnSkip) {
          markComplete(options.completeUrl);
        }
      }
      document.removeEventListener("keydown", onKey);
      clearHighlight();
      overlay.remove();
      spotlight.remove();
      tooltip.remove();
      activeRun = null;
      if (lastFocus && lastFocus.focus) {
        try {
          lastFocus.focus();
        } catch (_e) {}
      }
    }

    function showStep() {
      if (idx >= steps.length) {
        finish("complete");
        return;
      }
      var step = steps[idx];
      var sel = step.selector || "[data-tour='" + step.code + "']";
      var el = document.querySelector(sel);
      clearHighlight();
      stepLabel.textContent = formatStepOf(i18n, idx + 1, steps.length);
      titleEl.textContent = step.title || step.code;
      if (step.body) {
        bodyEl.textContent = step.body;
        bodyEl.hidden = false;
      } else {
        bodyEl.textContent = "";
        bodyEl.hidden = true;
      }
      if (!el) {
        missingEl.textContent = i18n.target_missing || "Target not visible.";
        missingEl.hidden = false;
      } else {
        missingEl.hidden = true;
      }
      nextBtn.textContent =
        idx === steps.length - 1 ? i18n.done || "Done" : i18n.next || "Next";
      placeSpotlight(el);
      placeTooltip(el);
      nextBtn.focus();
      track("step", context);
    }

    function onKey(e) {
      if (e.key === "Escape") {
        e.preventDefault();
        finish("skip");
      }
    }

    skipBtn.addEventListener("click", function () {
      finish("skip");
    });
    nextBtn.addEventListener("click", function () {
      idx += 1;
      showStep();
    });
    overlay.addEventListener("click", function () {
      finish("skip");
    });

    document.addEventListener("keydown", onKey);
    track("start", context);
    showStep();

    activeRun = { close: function () { finish("skip"); } };
  }

  function fetchAndRun(context, options) {
    return fetchSteps(context).then(function (steps) {
      if (steps.length) {
        options = options || {};
        options.context = context;
        runTour(steps, options);
      }
    });
  }

  function marketingContextFromDom() {
    var body = document.body;
    if (!body || body.getAttribute("data-rmc-premium-shell") !== "marketing") return null;
    var slug = body.getAttribute("data-rmc-page-slug") || "";
    if (MARKETING_SLUG_TO_CONTEXT[slug]) return MARKETING_SLUG_TO_CONTEXT[slug];
    var el = document.querySelector("[data-marketing-tour-context]");
    if (el) return el.getAttribute("data-marketing-tour-context");
    if (document.querySelector("[data-tour^='product-tour-']")) {
      return "marketing_product_tour";
    }
    if (document.querySelector("[data-tour='mkt-hero']")) {
      return "marketing_home";
    }
    return null;
  }

  function pageContextFromDom() {
    var mkt = marketingContextFromDom();
    if (mkt) return mkt;
    var page = document.querySelector("[data-rmc-page]");
    if (!page) return null;
    return PAGE_SLUG_TO_CONTEXT[page.getAttribute("data-rmc-page")] || null;
  }

  function controlPlaneContext() {
    var p = window.location.pathname || "";
    if (/\/super\/trust\/?$/.test(p)) return "super_trust";
    if (p.indexOf("/super/migration/csv-diff") !== -1) return "super_migration";
    if (p.indexOf("/super/tools/governed-query") !== -1) return "super_governed";
    return null;
  }

  function initTriggers() {
    document.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-tour-trigger]");
      if (!btn) return;
      e.preventDefault();
      var ctx =
        btn.getAttribute("data-tour-trigger") ||
        btn.getAttribute("data-tour-context") ||
        "";
      var url = btn.getAttribute("data-tour-steps-url");
      var completeUrl = btn.getAttribute("data-tour-complete-url") || "";
      if (url) {
        fetch(url, { credentials: "same-origin" })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            var steps = (data && data.steps) || [];
            if (steps.length) {
              runTour(steps, {
                context: (data && data.context) || ctx,
                completeUrl: completeUrl,
              });
            }
          })
          .catch(function () {});
      } else if (ctx) {
        fetchAndRun(ctx, { completeUrl: completeUrl });
      }
    });
  }

  function initControlPlane() {
    var ctx = controlPlaneContext();
    if (!ctx) return;
    var fab = document.getElementById("cpTourFab");
    var btn = document.getElementById("cpTourStartBtn");
    if (!fab || !btn) return;
    fab.classList.remove("d-none");
    btn.addEventListener("click", function () {
      fetchAndRun(ctx, {});
    });
  }

  function initPageFab() {
    var ctx = pageContextFromDom();
    if (!ctx || controlPlaneContext()) return;
    var isPublic = getBootScript() && getBootScript().getAttribute("data-tour-public") === "1";
    if (document.getElementById("rmcTourFab")) return;
    var i18n = getI18n();
    var wrap = document.createElement("div");
    wrap.id = "rmcTourFab";
    wrap.className = "rmc-tour-fab position-fixed bottom-0 end-0 p-3";
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = isPublic
      ? "btn btn-warning btn-sm shadow"
      : "btn btn-outline-primary btn-sm shadow";
    btn.textContent = i18n.start_tour || "Page tour";
    btn.setAttribute("aria-label", i18n.start_tour || "Page tour");
    btn.addEventListener("click", function () {
      fetchAndRun(ctx, {});
    });
    wrap.appendChild(btn);
    document.body.appendChild(wrap);
  }

  function initAutostart() {
    var cfg = readJsonScript("rmc-tour-page-config");
    var ctx = cfg.autostart || cfg.context || "";
    if (!ctx) return;
    var delay = typeof cfg.delayMs === "number" ? cfg.delayMs : 600;
    setTimeout(function () {
      fetchAndRun(ctx, {
        completeUrl: cfg.completeUrl || "",
        markCompleteOnSkip: true,
      });
    }, delay);
  }

  function boot() {
    initTriggers();
    initControlPlane();
    initPageFab();
    initAutostart();
    global.dispatchEvent(new CustomEvent("rmc-tour-ready"));
  }

  global.RMCTour = {
    run: runTour,
    fetchAndRun: fetchAndRun,
    fetchSteps: fetchSteps,
    initControlPlane: initControlPlane,
    initTriggers: initTriggers,
    pageContextFromDom: pageContextFromDom,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})(window);
