/*!
 * mkt-consent.js — GDPR-style cookie/analytics consent for the marketing site.
 *
 * Vanilla, framework-free, no inline handlers, CSP-clean (same-origin
 * {% static %} <script src> under script-src 'self', no nonce needed).
 *
 * DEFAULT-DENY: until the visitor makes a choice, only `necessary` is granted;
 * analytics + marketing are denied, so mkt-marketing-analytics.js withholds its
 * network sinks. The banner shows only when no prior choice exists.
 *
 * Public API (window.rmcConsent):
 *   .granted(category)  -> bool   (category: "necessary" | "analytics" | "marketing")
 *   .all()              -> object snapshot of the current choice
 *   .set({analytics, marketing})  persist a choice + close banner + notify
 *   .acceptAll() / .rejectNonEssential()  convenience setters
 *   .open()             reopen the preferences/banner UI
 *
 * On every change it dispatches CustomEvent("rmc:consent-changed", {detail})
 * on `document` and mirrors the choice to a first-party cookie (so the server
 * can read it later) plus localStorage.
 */
(function () {
  "use strict";

  if (typeof document === "undefined" || !document.addEventListener) {
    return;
  }

  var STORAGE_KEY = "rmc_consent_v1";
  var COOKIE_NAME = "rmc_consent_v1";
  var COOKIE_MAX_AGE = 60 * 60 * 24 * 180; // 180 days

  // Necessary is always on; analytics + marketing default OFF (deny).
  var state = { necessary: true, analytics: false, marketing: false, decided: false };

  function readStored() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) {
        return JSON.parse(raw);
      }
    } catch (err) {
      /* localStorage blocked/unavailable */
    }
    // Fall back to the cookie (e.g. localStorage disabled in private mode).
    try {
      var m = document.cookie.match(
        new RegExp("(?:^|; )" + COOKIE_NAME + "=([^;]*)")
      );
      if (m) {
        return JSON.parse(decodeURIComponent(m[1]));
      }
    } catch (err) {
      /* cookie unreadable */
    }
    return null;
  }

  function persist() {
    var payload = {
      necessary: true,
      analytics: !!state.analytics,
      marketing: !!state.marketing,
      decided: !!state.decided
    };
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch (err) {
      /* ignore */
    }
    try {
      var secure = window.location && window.location.protocol === "https:"
        ? "; Secure"
        : "";
      document.cookie =
        COOKIE_NAME +
        "=" +
        encodeURIComponent(JSON.stringify(payload)) +
        "; Max-Age=" +
        COOKIE_MAX_AGE +
        "; Path=/; SameSite=Lax" +
        secure;
    } catch (err) {
      /* ignore */
    }
  }

  function notify() {
    try {
      document.dispatchEvent(
        new CustomEvent("rmc:consent-changed", { detail: api.all() })
      );
    } catch (err) {
      /* CustomEvent unsupported */
    }
  }

  // ── Banner DOM wiring ──────────────────────────────────────────────────────
  function banner() {
    return document.querySelector("[data-mkt-consent]");
  }

  function showBanner(show) {
    var el = banner();
    if (!el) {
      return;
    }
    el.hidden = !show;
    el.setAttribute("aria-hidden", show ? "false" : "true");
  }

  function showPrefs(show) {
    var el = banner();
    if (!el) {
      return;
    }
    var panel = el.querySelector("[data-mkt-consent-prefs]");
    if (panel) {
      panel.hidden = !show;
    }
    // Sync the toggle checkboxes to current state when opening.
    if (show) {
      var a = el.querySelector("[data-mkt-consent-toggle='analytics']");
      var m = el.querySelector("[data-mkt-consent-toggle='marketing']");
      if (a) {
        a.checked = !!state.analytics;
      }
      if (m) {
        m.checked = !!state.marketing;
      }
    }
  }

  var api = {
    granted: function (category) {
      if (category === "necessary") {
        return true;
      }
      return !!state[category];
    },
    all: function () {
      return {
        necessary: true,
        analytics: !!state.analytics,
        marketing: !!state.marketing,
        decided: !!state.decided
      };
    },
    set: function (choice) {
      choice = choice || {};
      state.analytics = !!choice.analytics;
      state.marketing = !!choice.marketing;
      state.decided = true;
      persist();
      showBanner(false);
      notify();
    },
    acceptAll: function () {
      api.set({ analytics: true, marketing: true });
    },
    rejectNonEssential: function () {
      api.set({ analytics: false, marketing: false });
    },
    open: function () {
      showBanner(true);
      showPrefs(true);
    }
  };

  window.rmcConsent = api;

  function wire() {
    var el = banner();
    if (!el) {
      return;
    }

    el.addEventListener("click", function (ev) {
      var t = ev.target;
      if (!t || !t.closest) {
        return;
      }
      if (t.closest("[data-mkt-consent-accept]")) {
        ev.preventDefault();
        api.acceptAll();
      } else if (t.closest("[data-mkt-consent-reject]")) {
        ev.preventDefault();
        api.rejectNonEssential();
      } else if (t.closest("[data-mkt-consent-prefs-open]")) {
        ev.preventDefault();
        showPrefs(true);
      } else if (t.closest("[data-mkt-consent-save]")) {
        ev.preventDefault();
        var a = el.querySelector("[data-mkt-consent-toggle='analytics']");
        var m = el.querySelector("[data-mkt-consent-toggle='marketing']");
        api.set({ analytics: a && a.checked, marketing: m && m.checked });
      }
    });

    // Any element marked data-mkt-consent-open (e.g. a footer "Cookie settings"
    // link anywhere on the page) reopens the preferences UI.
    document.addEventListener("click", function (ev) {
      var t = ev.target;
      if (t && t.closest && t.closest("[data-mkt-consent-open]")) {
        ev.preventDefault();
        api.open();
      }
    });

    // Show the banner only if the visitor hasn't decided yet.
    showBanner(!state.decided);
  }

  // ── Init ───────────────────────────────────────────────────────────────────
  var stored = readStored();
  if (stored && typeof stored === "object") {
    state.analytics = !!stored.analytics;
    state.marketing = !!stored.marketing;
    state.decided = !!stored.decided;
  }
  // Notify subscribers of the initial (stored or default-deny) state so
  // already-loaded analytics can start emitting if consent was granted before.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      wire();
      notify();
    });
  } else {
    wire();
    notify();
  }
})();
