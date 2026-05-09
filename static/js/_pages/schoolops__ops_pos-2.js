(function() {
  var sel = document.getElementById('pos-inventory-pick');
  var lab = document.getElementById('pos-item-label');
  if (!sel || !lab) return;
  sel.addEventListener('change', function() {
    var opt = sel.options[sel.selectedIndex];
    if (opt && opt.value && opt.dataset.label) lab.value = opt.dataset.label;
  });
})();
