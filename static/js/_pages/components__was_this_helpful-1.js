(function(){
  var pageDataEl=document.getElementById("page-data-components__was_this_helpful-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["components__was_this_helpful-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var container = document.currentScript && document.currentScript.closest('.was-this-helpful');
  if (!container) return;
  var btns = container.querySelectorAll('.was-helpful-btn');
  var thanks = container.querySelector('.was-helpful-thanks');
  var storageKey = 'was_helpful_' + (container.querySelector('[data-feedback-id]') && container.querySelector('[data-feedback-id]').getAttribute('data-feedback-id') || 'page');
  function markDone() {
    btns.forEach(function(b) { b.disabled = true; });
    if (thanks) thanks.classList.remove('d-none');
    try { localStorage.setItem(storageKey, '1'); } catch (e) {}
  }
  try {
    if (localStorage.getItem(storageKey)) markDone();
  } catch (e) {}
  btns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      var helpful = this.getAttribute('data-helpful');
      if (typeof window.showToast === 'function') {
        window.showToast(helpful === 'yes' ? ((window.__RMC_PAGE_DATA__["components__was_this_helpful-1"] || {})["trans_thanks_for_your_feedback"]) : '{% trans "We\'ll use your feedback to improve." %}', helpful === 'yes' ? 'success' : 'info', 2500);
      }
      markDone();
    });
  });
})();
})();
