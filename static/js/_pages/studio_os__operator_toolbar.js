// Manager Studio: auto-submit tenant switcher on change (optional Apply still works).
(function () {
  var toolbar = document.querySelector('[data-studio-operator-toolbar="1"]');
  if (!toolbar) return;
  var select = toolbar.querySelector('[data-studio-school-select="1"]');
  var form = toolbar.querySelector('.studio-operator-toolbar__school-form');
  if (!select || !form) return;
  select.addEventListener('change', function () {
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });
})();
