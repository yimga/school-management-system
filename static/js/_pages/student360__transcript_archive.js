(function() {
  var modal = document.getElementById('freezeModal');
  if (!modal) return;
  var form = document.querySelector('form[action*="transcript-freeze"]');
  var yearSelect = document.getElementById('freeze_year_select');
  var yearHidden = document.getElementById('freeze_year_id');
  var submitBtn = document.getElementById('freezeSubmit');
  if (form && yearSelect && yearHidden && submitBtn) {
    submitBtn.addEventListener('click', function() {
      var val = yearSelect.value;
      if (!val) return;
      yearHidden.value = val;
      form.submit();
    });
  }
})();
