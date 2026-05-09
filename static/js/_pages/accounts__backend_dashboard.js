  (function () {
    var apply = function () {
      if (!document.body) return;
      document.body.dataset.dashboardPage = 'backend';
      document.body.classList.add('dashboard-page-backend');

      var allowed = { executive: true, operational: true, analytical: true };
      var params = new URLSearchParams(window.location.search);
      var fromUrl = (params.get('style') || params.get('preset') || '').toLowerCase();
      var root = document.getElementById('dashboard-layout');
      var fromData = root ? String(root.dataset.stylePreset || '').toLowerCase() : '';
      var fromTile = root ? String(root.dataset.tileVariant || '').toLowerCase() : '';
      var preset = 'executive';
      if (allowed[fromUrl]) {
        preset = fromUrl;
      } else if (allowed[fromData]) {
        preset = fromData;
      } else if (fromTile === 'compact') {
        preset = 'operational';
      } else if (fromTile === 'flat') {
        preset = 'analytical';
      }
      document.body.classList.remove('backend-preset-executive', 'backend-preset-operational', 'backend-preset-analytical');
      document.body.classList.add('backend-preset-' + preset);
      document.body.dataset.backendPreset = preset;
      if (root) root.dataset.stylePreset = preset;
    };

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', apply, { once: true });
    } else {
      apply();
    }
  })();
