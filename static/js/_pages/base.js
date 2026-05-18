      // Apply server-stored theme preference early (before CSS paints).
      // v3 contract (2026-05-18): data-theme carries the EFFECTIVE theme
      // (light|dark), never the raw preference. Mirrors theme-preference-bootstrap.js.
      // Preference (which may be "system") goes in data-theme-preference. Removing
      // data-theme on system pref — the old behavior — left every [data-theme="dark"]
      // CSS rule unmatched whenever the OS preferred dark, producing white-text-on-
      // white-card across every dashboard.
      (function () {
        const key = 'runmycampus-theme-preference';
        const html = document.documentElement;
        const valid = { light: 1, dark: 1, system: 1 };
        let pref = (html.getAttribute('data-theme-preference')
                 || html.getAttribute('data-theme')
                 || 'system').toLowerCase();
        try {
          var stored = localStorage.getItem(key);
          if (stored) pref = stored.toLowerCase();
        } catch (e) {}
        if (pref === 'auto') pref = 'system';
        if (!valid[pref]) pref = 'system';
        var resolved = pref;
        if (pref === 'system') {
          resolved = (window.matchMedia
            && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
        }
        html.setAttribute('data-theme', resolved);
        html.setAttribute('data-theme-preference', pref);
        html.setAttribute('data-resolved-theme', resolved);
        html.setAttribute('data-bs-theme', resolved);
        try { localStorage.setItem(key, pref); } catch (e) {}
      })();
    
