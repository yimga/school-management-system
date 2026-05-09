(function() {
  var schoolSelect = document.getElementById('rollback-school');
  var bundleSelect = document.getElementById('rollback-bundle');
  if (!schoolSelect || !bundleSelect) return;
  function filterBundles() {
    var sid = schoolSelect.value;
    for (var i = 0; i < bundleSelect.options.length; i++) {
      var opt = bundleSelect.options[i];
      if (opt.value === '') { opt.style.display = ''; continue; }
      opt.style.display = (opt.getAttribute('data-school-id') === sid) ? '' : 'none';
    }
    bundleSelect.value = '';
  }
  schoolSelect.addEventListener('change', filterBundles);
})();
