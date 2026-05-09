(function() {
  var totalEl = document.getElementById('id_total_amount');
  var amountIds = ['id_amount_1', 'id_amount_2', 'id_amount_3', 'id_amount_4', 'id_amount_5'];
  var summaryEl = document.getElementById('split-summary');
  var submitBtn = document.getElementById('split-submit-btn');
  var formEl = document.getElementById('split-allocation-form');

  function parseNum(val) {
    if (val === '' || val == null) return 0;
    var n = parseFloat(String(val).replace(/,/g, ''));
    return isNaN(n) ? 0 : n;
  }

  function updateSum() {
    var total = parseNum(totalEl && totalEl.value);
    var sum = 0;
    amountIds.forEach(function(id) {
      var el = document.getElementById(id);
      if (el) sum += parseNum(el.value);
    });
    if (!summaryEl) return;
    summaryEl.textContent = 'Sum: ' + sum.toFixed(2) + ' / Total: ' + total.toFixed(2);
    if (total > 0 && Math.abs(sum - total) > 0.001) {
      summaryEl.className = 'small mb-2 text-danger';
      if (submitBtn) submitBtn.disabled = true;
    } else {
      summaryEl.className = 'small mb-2 text-success';
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  function init() {
    amountIds.forEach(function(id) {
      var el = document.getElementById(id);
      if (el) {
        el.addEventListener('input', updateSum);
        el.addEventListener('change', updateSum);
      }
    });
    if (totalEl) {
      totalEl.addEventListener('input', updateSum);
      totalEl.addEventListener('change', updateSum);
    }
    updateSum();
  }

  if (formEl) {
    formEl.addEventListener('submit', function() {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span> Recording…';
      }
    });
    if (window.FormDraftSave) window.FormDraftSave.init(formEl);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
