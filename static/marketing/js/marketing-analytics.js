(function () {
  "use strict";

  var ALLOWED_KEYS = {
    event_name: true,
    page_path: true,
    page_type: true,
    page_slug: true,
    cta_label: true,
    cta_location: true,
    menu_name: true,
    link_label: true,
    link_target: true,
    form_name: true,
    form_stage: true,
    plan_name: true,
    resource_type: true,
    scroll_depth: true,
    timestamp: true
  };
  var firedForms = {};
  var firedDepths = {};

  function readConfig() {
    var el = document.getElementById("rmc-marketing-analytics-config");
    if (!el) return {};
    try {
      return JSON.parse(el.textContent || "{}") || {};
    } catch (err) {
      return {};
    }
  }

  var config = readConfig();

  function textOf(el) {
    return ((el && (el.getAttribute("aria-label") || el.textContent)) || "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 120);
  }

  function clean(payload) {
    var out = {};
    Object.keys(payload || {}).forEach(function (key) {
      if (!ALLOWED_KEYS[key]) return;
      var value = payload[key];
      if (value === undefined || value === null || value === "") return;
      out[key] = typeof value === "string" ? value.slice(0, 256) : value;
    });
    out.event_name = String(out.event_name || "unknown").slice(0, 80);
    out.page_path = String(out.page_path || window.location.pathname).slice(0, 256);
    out.page_type = String(out.page_type || config.page_type || document.documentElement.dataset.rmcPageType || "marketing").slice(0, 80);
    out.page_slug = String(out.page_slug || config.page_slug || document.documentElement.dataset.rmcPageSlug || "unknown").slice(0, 120);
    out.timestamp = out.timestamp || new Date().toISOString();
    return out;
  }

  function emit(payload) {
    var event = clean(payload);
    window.rmcMarketingAnalyticsEvents = window.rmcMarketingAnalyticsEvents || [];
    window.rmcMarketingAnalyticsEvents.push(event);
    window.dispatchEvent(new CustomEvent("rmc:marketing-analytics", { detail: event }));
    if (!config.endpoint) return;
    var body = JSON.stringify(event);
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(config.endpoint, new Blob([body], { type: "application/json" }));
      } else {
        fetch(config.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: body,
          keepalive: true,
          credentials: "omit"
        });
      }
    } catch (err) {
      /* Analytics must never break the marketing surface. */
    }
  }

  function closest(el, selector) {
    return el && el.closest ? el.closest(selector) : null;
  }

  document.addEventListener("DOMContentLoaded", function () {
    emit({ event_name: "page_view" });
    var params = new URLSearchParams(window.location.search || "");
    if (params.has("submitted")) {
      emit({ event_name: "form_submit_success", form_name: document.documentElement.dataset.rmcPageSlug || "marketing", form_stage: "success" });
    } else if (params.has("error")) {
      emit({ event_name: "form_submit_error", form_name: document.documentElement.dataset.rmcPageSlug || "marketing", form_stage: "error" });
    }
  });

  document.addEventListener("click", function (ev) {
    var target = ev.target;
    var cta = closest(target, "[data-cta]");
    if (cta) {
      emit({
        event_name: "cta_click",
        cta_label: cta.getAttribute("data-cta-label") || textOf(cta),
        cta_location: cta.getAttribute("data-cta-location") || cta.getAttribute("data-page") || "body",
        link_target: cta.getAttribute("href") || ""
      });
      if (cta.getAttribute("data-plan-name")) {
        emit({ event_name: "pricing_plan_interest", plan_name: cta.getAttribute("data-plan-name") });
      }
      return;
    }
    var menuLink = closest(target, "[data-menu-link]");
    if (menuLink) {
      emit({
        event_name: "menu_link_click",
        menu_name: menuLink.getAttribute("data-menu-name") || "navigation",
        link_label: menuLink.getAttribute("data-link-label") || textOf(menuLink),
        link_target: menuLink.getAttribute("data-link-target") || menuLink.getAttribute("href") || ""
      });
      return;
    }
    var resource = closest(target, "[data-resource-type]");
    if (resource) {
      emit({
        event_name: "resource_click",
        resource_type: resource.getAttribute("data-resource-type"),
        link_label: resource.getAttribute("data-link-label") || textOf(resource),
        link_target: resource.getAttribute("href") || ""
      });
    }
  });

  document.addEventListener("show.bs.dropdown", function (ev) {
    var el = ev.target;
    emit({ event_name: "menu_open", menu_name: el.getAttribute("data-menu-name") || textOf(el) || "navigation" });
  });

  document.addEventListener("focusin", function (ev) {
    var form = closest(ev.target, "form[data-form-name]");
    if (!form) return;
    var name = form.getAttribute("data-form-name") || "marketing";
    if (firedForms[name]) return;
    firedForms[name] = true;
    emit({ event_name: "form_start", form_name: name, form_stage: "start" });
  });

  document.addEventListener("submit", function (ev) {
    var form = closest(ev.target, "form[data-form-name]");
    if (!form) return;
    emit({ event_name: "form_submit_attempt", form_name: form.getAttribute("data-form-name") || "marketing", form_stage: "attempt" });
  }, true);

  window.addEventListener("scroll", function () {
    var doc = document.documentElement;
    var max = Math.max(1, doc.scrollHeight - window.innerHeight);
    var depth = Math.min(100, Math.round((window.scrollY / max) * 100));
    [25, 50, 75, 100].forEach(function (mark) {
      if (depth >= mark && !firedDepths[mark]) {
        firedDepths[mark] = true;
        emit({ event_name: "scroll_milestone", scroll_depth: mark });
      }
    });
  }, { passive: true });
})();
