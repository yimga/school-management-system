  (function() {
    var ta = document.getElementById('letter_body');
    var countEl = document.getElementById('letter-body-count');
    if (ta && countEl) {
      function updateCount() {
        var n = (ta.value || '').length;
        countEl.textContent = n.toLocaleString() + ' / 100,000';
        countEl.classList.toggle('text-danger', n > 100000);
      }
      ta.addEventListener('input', updateCount);
      ta.addEventListener('keyup', updateCount);
      updateCount();
    }
    var sel = document.getElementById('classroom_id');
    var countSpan = document.getElementById('classroom-student-count');
    if (sel && countSpan) {
      function updatePreview() {
        var opt = sel.options[sel.selectedIndex];
        var n = opt && opt.value ? parseInt(opt.getAttribute('data-count'), 10) : 0;
        countSpan.textContent = n > 0 ? n + ' letter' + (n !== 1 ? 's' : '') + ' will be generated' : '';
      }
      sel.addEventListener('change', updatePreview);
      updatePreview();
    }
  })();
  
