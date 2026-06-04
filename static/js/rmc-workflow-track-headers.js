/**
 * Workflow Progress Bus — client opt-in for HTTP write tracking (v4.01.18).
 *
 * Patches fetch / XHR / htmx to send ``X-RMC-Workflow-Track: 1`` on API-like
 * mutating requests so ``WorkflowProgressRequestMiddleware`` can envelope
 * long operator/tenant writes without flashing the chip on every /super/ form.
 *
 * Load synchronously (no defer) before page bundles that call fetch().
 */
(function () {
  "use strict";

  if (window.__rmcWorkflowTrackHeadersMounted) return;
  window.__rmcWorkflowTrackHeadersMounted = true;

  var HEADER = "X-RMC-Workflow-Track";
  var VALUE = "1";

  var API_PATH_RE =
    /\/(?:api\/v\d+|api|super\/api|portal\/api|assist-dock|t\/[^/]+\/api)\//i;

  function pathFromUrl(url) {
    if (!url || typeof url !== "string") return "";
    try {
      if (url.indexOf("http") === 0) return new URL(url).pathname || "";
      return new URL(url, window.location.origin).pathname || "";
    } catch (_e) {
      return url.split("?")[0] || "";
    }
  }

  function shouldTrackUrl(url) {
    var path = pathFromUrl(url);
    if (!path) return false;
    if (API_PATH_RE.test(path)) return true;
    return false;
  }

  function shouldTrackElement(el) {
    if (!el || !el.closest) return false;
    return !!el.closest("[data-rmc-workflow-track]");
  }

  function mergeInit(init) {
    var next = init ? Object.assign({}, init) : {};
    var headers = new Headers(next.headers || {});
    if (!headers.has(HEADER)) headers.set(HEADER, VALUE);
    next.headers = headers;
    return next;
  }

  function nativeFetch(input, init) {
    return window.__rmcNativeFetch(input, init);
  }

  window.__rmcNativeFetch = window.__rmcNativeFetch || window.fetch.bind(window);

  window.fetch = function (input, init) {
    var url =
      typeof input === "string"
        ? input
        : input && typeof input.url === "string"
          ? input.url
          : "";
    var track =
      shouldTrackUrl(url) || (init && init.rmcWorkflowTrack) || false;
    if (track) init = mergeInit(init);
    if (init && init.rmcWorkflowTrack) delete init.rmcWorkflowTrack;
    return nativeFetch(input, init);
  };

  var xhrOpen = XMLHttpRequest.prototype.open;
  var xhrSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (method, url) {
    this._rmcWorkflowTrackUrl = url;
    this._rmcWorkflowTrackMethod = method;
    return xhrOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function (body) {
    if (shouldTrackUrl(this._rmcWorkflowTrackUrl || "")) {
      try {
        this.setRequestHeader(HEADER, VALUE);
      } catch (_e) {
        /* duplicate header on retry */
      }
    }
    return xhrSend.apply(this, arguments);
  };

  document.addEventListener(
    "htmx:configRequest",
    function (evt) {
      if (!evt || !evt.detail) return;
      var path = evt.detail.path || "";
      var el = evt.target;
      if (!shouldTrackUrl(path) && !shouldTrackElement(el)) return;
      evt.detail.headers = evt.detail.headers || {};
      evt.detail.headers[HEADER] = VALUE;
    },
    true
  );

  /** Explicit helper for page bundles that build custom fetch opts. */
  window.rmcWorkflowTrackFetch = function (url, init) {
    init = mergeInit(init || {});
    return window.fetch(url, init);
  };
})();
