// Preview labels loader — reads localized label strings from a JSON data
// island and exposes them on window. CSP-safe replacement for the previous
// inline <script> in portal_base.html.
(function () {
  var el = document.getElementById('rmc-preview-labels');
  if (!el) return;
  try {
    var labels = JSON.parse(el.textContent || '{}');
    if (labels.default) window.PREVIEW_DEFAULT_LABEL = labels.default;
    if (labels.dismiss) window.PREVIEW_DISMISS_LABEL = labels.dismiss;
  } catch (_e) { /* ignore */ }
})();
