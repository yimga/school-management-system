(function() {
  var key = 'table-density-evaluation_admin';
  var wrapper = document.querySelector('[data-table-density-key="evaluation_admin"]');
  if (!wrapper) return;
  var table = wrapper.querySelector('table');
  var condensed = localStorage.getItem(key) === 'condensed';
  function apply() {
    if (table) table.classList.toggle('table-condensed', condensed);
    wrapper.querySelectorAll('.table-density-toggle [data-density]').forEach(function(btn) {
      btn.classList.toggle('active', (btn.getAttribute('data-density') === 'condensed') === condensed);
    });
  }
  apply();
  wrapper.querySelectorAll('.table-density-toggle [data-density]').forEach(function(btn) {
    btn.addEventListener('click', function() {
      condensed = this.getAttribute('data-density') === 'condensed';
      localStorage.setItem(key, condensed ? 'condensed' : 'expanded');
      apply();
    });
  });
})();
