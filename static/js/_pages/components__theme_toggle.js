document.addEventListener('DOMContentLoaded', function() {
  const themeToggle = document.getElementById('themeToggle');
  const themeSelector = document.getElementById('themeSelector');
  const themeLabel = document.getElementById('themeLabel');
  const htmlElement = document.documentElement;
  const adminDefault = (htmlElement.dataset.adminTheme || 'system').toLowerCase();

  function updateMetaThemeColor(theme) {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) return;
    const useDarkMeta = theme === 'dark' || theme === 'high_contrast';
    const prop = useDarkMeta ? '--meta-theme-color-dark' : '--meta-theme-color-light';
    const value = getComputedStyle(htmlElement).getPropertyValue(prop).trim();
    if (value) meta.setAttribute('content', value);
  }

  // initialize selector to admin default
  themeSelector.value = adminDefault === 'system' ? 'system' : adminDefault;

  // Load saved theme preference or fall back to admin default (supports system)
  const savedTheme = localStorage.getItem('theme');
  const initial = savedTheme || adminDefault || 'system';
  setTheme(resolveTheme(initial), !!savedTheme);

  // Toggle button cycles light/dark quickly
  themeToggle.addEventListener('click', function() {
    const currentTheme = htmlElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme, true);
  });

  // Selector supports all modes
  themeSelector.addEventListener('change', (e) => {
    const choice = e.target.value;
    if (choice === 'system') {
      localStorage.removeItem('theme');
      setTheme(resolveTheme('system'), false);
    } else {
      setTheme(choice, true);
    }
  });

  function resolveTheme(pref) {
    if (pref === 'system') {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      return prefersDark ? 'dark' : 'light';
    }
    return pref;
  }

  function setTheme(theme, persist = false) {
    htmlElement.setAttribute('data-theme', theme);
    themeSelector.value = persist ? theme : (localStorage.getItem('theme') || adminDefault || 'system');
    themeLabel.textContent = labelFor(theme);
    if (persist) {
      localStorage.setItem('theme', theme);
    }

    updateMetaThemeColor(theme);

    // Dispatch custom event for other components
    window.dispatchEvent(new CustomEvent('theme-changed', { detail: { theme } }));
  }

  function labelFor(theme) {
    switch (theme) {
      case 'dark': return 'Dark';
      case 'classic': return 'Classic';
      case 'high_contrast': return 'High contrast';
      case 'light': return 'Light';
      default: return 'System';
    }
  }

  // Listen for system theme changes when user is following system
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    if (!localStorage.getItem('theme') && (adminDefault === 'system')) {
      setTheme(e.matches ? 'dark' : 'light');
    }
  });
});
