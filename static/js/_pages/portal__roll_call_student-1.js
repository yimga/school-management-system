(function(){
  var pageDataEl=document.getElementById("page-data-portal__roll_call_student-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["portal__roll_call_student-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
    var presentVal = '(window.__RMC_PAGE_DATA__["portal__roll_call_student-1"]||{})["var_attendance_present"]';
    document.getElementById('mark-all-present')?.addEventListener('click', function() {
      document.querySelectorAll('.status-select').forEach(function(s) { s.value = presentVal; });
    });
    document.getElementById('save-all-present')?.addEventListener('click', function() {
      document.querySelectorAll('.status-select').forEach(function(s) { s.value = presentVal; });
      this.closest('form').submit();
    });
    (function() {
      if (navigator.onLine || !window.SMSOfflineDB || !window.SMSOfflineDB.getClassrooms) return;
      var el = document.getElementById('sms-roll-call-offline-cache');
      if (!el) return;
      el.classList.remove('d-none');
      Promise.all([window.SMSOfflineDB.getClassrooms(), window.SMSOfflineDB.getStudents()]).then(function(res) {
        var classrooms = res[0] || [];
        var students = res[1] || [];
        el.textContent = 'Offline: ' + classrooms.length + ' class(es) and ' + students.length + ' student(s) cached. Choose date and class when back online to take attendance.';
      }).catch(function() {
        el.textContent = 'Offline. Cached data may be available after you sync when online.';
      });
    })();
  
})();
