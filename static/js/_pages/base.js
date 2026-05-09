      // Apply server-stored theme preference early (before CSS paints).
      (function () {
        const key = 'runmycampus-theme-preference';
        const html = document.documentElement;
        let pref = (html.getAttribute('data-theme') || 'system').toLowerCase();
        try {
          var stored = localStorage.getItem(key);
          if (stored) pref = stored.toLowerCase();
        } catch (e) {}
        if (pref === 'system' || pref === 'auto') {
          html.removeAttribute('data-theme');
          html.removeAttribute('data-bs-theme');
          try { localStorage.removeItem(key); } catch (e) {}
          return;
        }
        html.setAttribute('data-theme', pref);
        html.setAttribute('data-bs-theme', pref);
        try { localStorage.setItem(key, pref); } catch (e) {}
      })();
    
