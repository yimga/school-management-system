// User-dropdown keyboard shortcuts + idle indicator.
// Reads its URLs from a JSON data island (#user-dropdown-config) so the
// template stays free of inline executable JS.
(function () {
  document.addEventListener('DOMContentLoaded', function () {
    var el = document.getElementById('user-dropdown-config');
    var cfg = {};
    if (el) {
      try { cfg = JSON.parse(el.textContent || '{}'); } catch (_e) { cfg = {}; }
    }

    document.addEventListener('keydown', function (e) {
      var dropdown = document.querySelector('.user-dropdown-menu.show');
      if (!dropdown) return;

      if (e.altKey) {
        switch (e.key.toLowerCase()) {
          case 'p':
            e.preventDefault();
            if (cfg.profileUrl) window.location.href = cfg.profileUrl;
            break;
          case 's':
            e.preventDefault();
            if (cfg.preferencesUrl) window.location.href = cfg.preferencesUrl;
            break;
          case 'l':
            e.preventDefault();
            if (cfg.logoutUrl) window.location.href = cfg.logoutUrl;
            break;
        }
      }

    });

    function updateUserStatus() {
      var indicator = document.querySelector('.user-status-indicator');
      if (!indicator) return;
      var lastActivity = Date.now();
      var idleTime = 5 * 60 * 1000;
      indicator.style.background = (Date.now() - lastActivity < idleTime) ? 'var(--ds-success)' : 'var(--ds-warning)';
    }
    setInterval(updateUserStatus, 60000);
    updateUserStatus();

    var lastActivityTime = Date.now();
    ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'].forEach(function (event) {
      document.addEventListener(event, function () { lastActivityTime = Date.now(); }, true);
    });
  });
})();
