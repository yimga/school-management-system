// VOC feedback widget — CSP-clean toggle.
// Replaces the inline <script> shim from templates/components/contextual_feedback_widget.html.
(function () {
  function init() {
    var widgets = document.querySelectorAll('.voc-widget');
    widgets.forEach(function (widget) {
      var toggle = widget.querySelector('[data-voc-toggle]');
      if (!toggle) return;
      toggle.addEventListener('click', function () {
        widget.dataset.open = widget.dataset.open === 'true' ? 'false' : 'true';
      });
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
