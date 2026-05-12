/**
 * Theme preference bootstrap — runs before <body> to avoid flash-of-wrong-theme.
 * v2 (2026-05-12): three-mode contract.
 *
 *   <html data-theme="light|dark|system">   ← the user's *preference*
 *   <html data-resolved-theme="light|dark"> ← the *effective* theme (always set)
 *   <html data-bs-theme="light|dark">       ← Bootstrap 5 compat (mirrors resolved)
 *
 * When preference is "system" we listen for OS theme changes and live-update
 * data-resolved-theme + data-bs-theme so the UI flips without a reload.
 *
 * The toggle in user_dropdown.html writes to localStorage[KEY] and dispatches
 * a `rmc:theme-change` CustomEvent; this bootstrap listens for that too so the
 * three buttons (Light / Dark / System) can re-apply without a page refresh.
 *
 * Externalised from portal_base.html for CSP friendliness (no inline scripts).
 */
(function () {
  "use strict";
  var KEY = "runmycampus-theme-preference";
  var VALID = { light: 1, dark: 1, system: 1 };
  var mql = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function readPreference() {
    var raw = null;
    try { raw = localStorage.getItem(KEY); } catch (_) { /* private mode */ }
    return VALID[raw] ? raw : "system";
  }

  function resolve(pref) {
    if (pref === "system") {
      return (mql && mql.matches) ? "dark" : "light";
    }
    return pref;
  }

  function apply(pref) {
    var resolved = resolve(pref);
    var root = document.documentElement;
    root.setAttribute("data-theme", pref);
    root.setAttribute("data-resolved-theme", resolved);
    root.setAttribute("data-bs-theme", resolved);
    /* Hook for native browser UI (scrollbars, form controls) — only meaningful
       value is light|dark, so we mirror the resolved value. */
    root.style.colorScheme = resolved;
  }

  /* Theme v2 (2026-05-12, Phase J end-to-end): propagate the tenant's neutral
     palette choice (cool | warm) onto <html> so the [data-rmc-neutral] CSS
     overrides in design-tokens.css activate platform-wide, not just on the
     portal shell. Reads from a meta tag emitted by the siteconfig context
     processor or any inline server render. Falls back to "cool". */
  function applyNeutralPalette() {
    var root = document.documentElement;
    /* If an authoring template already set it on body or html, respect that. */
    var fromBody = document.body && document.body.getAttribute("data-rmc-neutral");
    var fromHtml = root.getAttribute("data-rmc-neutral");
    var fromMeta = (function () {
      var m = document.querySelector('meta[name="rmc-neutral-palette"]');
      return m ? (m.getAttribute("content") || "").trim().toLowerCase() : "";
    })();
    var value = (fromBody || fromHtml || fromMeta || "cool").toLowerCase();
    if (value !== "cool" && value !== "warm") { value = "cool"; }
    root.setAttribute("data-rmc-neutral", value);

    /* Theme v2 (2026-05-12, Phase J end-to-end): also propagate the tenant
       brand gradient overrides from <meta> into CSS variables on <html>. This
       way the typed-column values from RuntimeDefaults flow into the cascade
       on every shell, not just portal_base (which had inline injection). */
    var endMeta = document.querySelector('meta[name="rmc-brand-gradient-end"]');
    if (endMeta && endMeta.getAttribute("content")) {
      root.style.setProperty("--brand-gradient-end", endMeta.getAttribute("content"));
    }
    var angleMeta = document.querySelector('meta[name="rmc-brand-gradient-angle"]');
    if (angleMeta && angleMeta.getAttribute("content")) {
      root.style.setProperty("--brand-gradient-angle", angleMeta.getAttribute("content"));
    }
    /* v2 carried-forward (2026-05-12): expose tenant logo URLs as CSS custom
       properties on <html> so .rmc-logo-adaptive can swap the light/dark variant
       via a single attribute selector ([data-resolved-theme="dark"]). The light
       URL is always set; the dark URL is only set when the tenant supplied one
       (otherwise the rule cascade falls through to --site-logo-url). */
    var logoMeta = document.querySelector('meta[name="rmc-site-logo"]');
    if (logoMeta && logoMeta.getAttribute("content")) {
      root.style.setProperty("--site-logo-url", "url(\"" + logoMeta.getAttribute("content") + "\")");
    }
    var logoDarkMeta = document.querySelector('meta[name="rmc-site-logo-dark"]');
    if (logoDarkMeta && logoDarkMeta.getAttribute("content")) {
      root.style.setProperty("--site-logo-dark-url", "url(\"" + logoDarkMeta.getAttribute("content") + "\")");
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyNeutralPalette);
  } else {
    applyNeutralPalette();
  }

  apply(readPreference());

  /* Live OS theme response — only relevant when preference is "system". */
  if (mql && typeof mql.addEventListener === "function") {
    mql.addEventListener("change", function () {
      if (readPreference() === "system") {
        apply("system");
      }
    });
  } else if (mql && typeof mql.addListener === "function") {
    /* Safari < 14 fallback */
    mql.addListener(function () {
      if (readPreference() === "system") {
        apply("system");
      }
    });
  }

  /* Cross-page sync: storage events fire in *other* tabs when localStorage
     changes. Plus a same-tab CustomEvent so the toggle UI updates instantly. */
  window.addEventListener("storage", function (e) {
    if (e.key === KEY) {
      apply(readPreference());
    }
  });
  window.addEventListener("rmc:theme-change", function () {
    apply(readPreference());
  });

  /* Server sync — fire-and-forget POST to persist preference across devices.
     Reads CSRF from the cookie. No-op if not authenticated (the endpoint will
     return 401/403 and we ignore). */
  function readCsrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : null;
  }
  function syncToServer(pref) {
    if (typeof fetch !== "function") { return; }
    var csrf = readCsrf();
    if (!csrf) { return; }
    fetch("/api/preferences/theme/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      credentials: "same-origin",
      body: JSON.stringify({ theme: pref })
    }).catch(function () { /* fire-and-forget */ });
  }

  /* Expose a tiny API for the toggle component (and for tests). */
  window.RMCTheme = {
    get: readPreference,
    set: function (pref) {
      if (!VALID[pref]) { pref = "system"; }
      try { localStorage.setItem(KEY, pref); } catch (_) {}
      apply(pref);
      try {
        window.dispatchEvent(new CustomEvent("rmc:theme-change", { detail: { preference: pref } }));
      } catch (_) {
        var ev = document.createEvent("Event");
        ev.initEvent("rmc:theme-change", true, true);
        window.dispatchEvent(ev);
      }
      syncToServer(pref);
    },
    resolved: function () { return resolve(readPreference()); }
  };
})();
