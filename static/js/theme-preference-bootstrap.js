/**
 * Theme preference bootstrap — runs before <body> to avoid flash-of-wrong-theme.
 *
 * v3 (2026-05-18) attribute contract — `data-theme` carries the EFFECTIVE
 * theme, never the literal preference string. This is the contract every
 * CSS rule across 34 files (271 selectors) expects, and the contract that
 * sibling scripts (`_pages/backend_base-1.js`) already follow:
 *
 *   <html data-theme="light|dark">             ← effective (== resolved)
 *   <html data-resolved-theme="light|dark">    ← effective (kept for sites that opted in)
 *   <html data-bs-theme="light|dark">          ← Bootstrap 5 compat
 *   <html data-theme-preference="light|dark|system">  ← raw preference (toggle UI only)
 *
 * Why v3 reverts the v2 "preference in data-theme" idea: when a user picked
 * "System" + OS=dark, v2 wrote `data-theme="system"`, which never matched
 * any `[data-theme="dark"]` CSS selector. Aesthetic-profile dark overrides
 * (e.g. `[data-rmc-aesthetic="cool-apple"][data-theme="dark"]` setting
 * `--surface-elevated: #1e293b`) silently skipped, while `[data-bs-theme="dark"]`
 * still flipped `--text-primary` to near-white. Result: white text on white
 * cards across every card/table on the platform whenever the operator's OS
 * was in dark mode and they had not explicitly picked Dark. v3 fixes it
 * at the source: `data-theme` is always light|dark.
 *
 * Toggle UI reads the preference via `RMCTheme.get()` (which still hits
 * localStorage), so the three buttons (Light / Dark / System) keep working.
 * Anything that needs the raw preference can read `data-theme-preference`.
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
    /* v3 contract (2026-05-18): data-theme carries the EFFECTIVE theme so
       every `[data-theme="dark"]` selector across the platform fires when
       the page is rendering dark, regardless of whether the user picked
       Dark explicitly or System-with-dark-OS. The raw preference moves to
       data-theme-preference for the toggle UI / any code that needs it. */
    root.setAttribute("data-theme", resolved);
    root.setAttribute("data-theme-preference", pref);
    root.setAttribute("data-resolved-theme", resolved);
    root.setAttribute("data-bs-theme", resolved);
    /* Hook for native browser UI (scrollbars, form controls) — only meaningful
       value is light|dark, so we mirror the resolved value. */
    root.style.colorScheme = resolved;
    /* Unfold / Tailwind dark: utilities require .dark on <html> (data-bs-theme alone is not enough). */
    if (resolved === "dark") {
      root.classList.add("dark");
    } else {
      root.classList.remove("dark");
    }
    syncPortalBackendBodyPalette(resolved);
  }

  var PORTAL_BACKEND_PALETTES = [
    "portal-backend-dark",
    "portal-backend-light",
    "portal-backend-sand",
    "portal-backend-snow",
    "portal-backend-cream",
    "portal-backend-lavender",
    "portal-backend-black",
    "portal-backend-ink",
    "portal-backend-onyx",
    "portal-backend-charcoal",
    "portal-backend-midnight",
  ];

  function syncPortalBackendBodyPalette(resolved) {
    if (!document.body) {
      return;
    }
    var i;
    for (i = 0; i < PORTAL_BACKEND_PALETTES.length; i++) {
      document.body.classList.remove(PORTAL_BACKEND_PALETTES[i]);
    }
    document.body.classList.add(
      resolved === "dark" ? "portal-backend-dark" : "portal-backend-light"
    );
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

    /* v2.42 (2026-05-15): aesthetic-profile cascade.
       Projects rmc-aesthetic-profile + 6 token overrides from <meta> into:
         - data-rmc-aesthetic="<profile>" attribute on <html>
         - --site-aesthetic-* CSS custom properties on <html>
       The CSS layer (rmc-warm-bright-school.css) consumes these via
       var(--site-aesthetic-surface-bg, <profile-default>) so tenant
       overrides always win, blank fields fall back to the platform default. */
    /* v2.47 (2026-05-15): per-user aesthetic override. Read localStorage first
       so a user picking "Cool Apple" or "Stone" in the Appearance dropdown can
       override the tenant default. Falls back to the meta-tag value (which is
       the tenant SiteSettings or platform default). */
    var userAestheticPref = null;
    try { userAestheticPref = localStorage.getItem("runmycampus-aesthetic-preference"); } catch (_) { /* private mode */ }
    var aestheticMeta = document.querySelector('meta[name="rmc-aesthetic-profile"]');
    var metaProfile = (aestheticMeta && (aestheticMeta.getAttribute("content") || "").trim().toLowerCase()) || "warm-bright";
    var profile = (userAestheticPref || metaProfile).toLowerCase();
    if (profile !== "warm-bright" && profile !== "cool-apple" && profile !== "stone") {
      profile = "warm-bright";
    }
    root.setAttribute("data-rmc-aesthetic", profile);

    var aestheticOverrides = [
      ["rmc-aesthetic-surface-bg",      "--site-aesthetic-surface-bg"],
      ["rmc-aesthetic-surface-canvas",  "--site-aesthetic-surface-canvas"],
      ["rmc-aesthetic-text-primary",    "--site-aesthetic-text-primary"],
      ["rmc-aesthetic-accent-warm",     "--site-aesthetic-accent-warm"],
      ["rmc-aesthetic-accent-success",  "--site-aesthetic-accent-success"],
      ["rmc-aesthetic-accent-danger",   "--site-aesthetic-accent-danger"],
    ];
    for (var i = 0; i < aestheticOverrides.length; i++) {
      var metaName = aestheticOverrides[i][0];
      var cssVar = aestheticOverrides[i][1];
      var m = document.querySelector('meta[name="' + metaName + '"]');
      if (m && m.getAttribute("content")) {
        root.style.setProperty(cssVar, m.getAttribute("content"));
      }
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyNeutralPalette);
  } else {
    applyNeutralPalette();
  }

  apply(readPreference());
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      apply(readPreference());
    });
  }

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

  /* v2.47 (2026-05-15): aesthetic-profile picker. The button group in
     user_dropdown.html writes to localStorage["runmycampus-aesthetic-preference"]
     and fires rmc:aesthetic-change so the cascade re-applies without a reload. */
  window.addEventListener("rmc:aesthetic-change", function () {
    applyNeutralPalette();
  });
  window.addEventListener("storage", function (e) {
    if (e.key === "runmycampus-aesthetic-preference") {
      applyNeutralPalette();
    }
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
