(function() {
  var sel = document.getElementById('object_type');
  var show = function(id, on) {
    var el = document.getElementById(id);
    if (el) el.style.display = on ? '' : 'none';
  };
  var update = function() {
    var v = (sel && sel.value) || 'entity';
    show('field-entity', v === 'entity');
    show('field-entity-code', v === 'field');
    show('field-field-name', v === 'field');
    show('field-package', v === 'package');
    show('field-consumer-type', v === 'consumer');
    show('field-consumer-code', v === 'consumer');
  };
  if (sel) { sel.addEventListener('change', update); update(); }
})();
