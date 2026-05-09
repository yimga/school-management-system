// RMC click-ingest loader — reads ingest URL + measurement phase from a JSON
// data island. CSP-safe replacement for the previous Django-interpolated
// inline script in portal_base.html.
(function () {
  var el = document.getElementById('rmc-click-ingest-config');
  if (!el) return;
  try {
    var cfg = JSON.parse(el.textContent || '{}');
    if (cfg.ingestUrl) window.__RMC_CLICK_INGEST = cfg.ingestUrl;
    if (cfg.phase) window.__RMC_CLICK_PHASE = cfg.phase;
  } catch (_e) { /* ignore malformed payload */ }
})();
