(function(){
  var pageDataEl=document.getElementById("page-data-portal__roll_call_teacher-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["portal__roll_call_teacher-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
    (function() {
      if (navigator.onLine || !window.SMSOfflineDB) return;
      var el = document.getElementById('sms-roll-call-teacher-offline');
      if (!el) return;
      el.classList.remove('d-none');
      el.textContent = 'Offline. Teacher list will load when you\'re back online. Use student attendance for cached class/student data when offline.';
    })();
    var presentVal = '(window.__RMC_PAGE_DATA__["portal__roll_call_teacher-1"]||{})["var_teacherattendance_present"]';
    document.getElementById('mark-all-present')?.addEventListener('click', function() {
      document.querySelectorAll('.status-select').forEach(function(s) { s.value = presentVal; });
    });
    document.getElementById('save-all-present')?.addEventListener('click', function() {
      document.querySelectorAll('.status-select').forEach(function(s) { s.value = presentVal; });
      this.closest('form').submit();
    });
  
})();
