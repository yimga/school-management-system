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
  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }
  function persistVote(feedbackId, helpful) {
    var endpoint = container.getAttribute('data-feedback-endpoint') || '';
    if (!endpoint || !window.fetch) return Promise.resolve(true);
    var body = new URLSearchParams();
    body.set('title', 'Helpful vote: ' + feedbackId);
    body.set('description', helpful === 'yes' ? 'Helpful' : 'Not helpful');
    body.set('category', 'workflow');
    body.set('module', feedbackId);
    body.set('route', window.location.pathname || '');
    body.set('severity', helpful === 'yes' ? 'low' : 'medium');
    return fetch(endpoint, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: body.toString()
    }).then(function(response) { return response.ok; });
  }
  try {
    if (localStorage.getItem(storageKey)) markDone();
  } catch (e) {}
  btns.forEach(function(btn) {
    btn.addEventListener('click', function() {
      var helpful = this.getAttribute('data-helpful');
      var feedbackId = this.getAttribute('data-feedback-id') || 'page';
      var copy = window.__RMC_PAGE_DATA__["components__was_this_helpful-1"] || {};
      persistVote(feedbackId, helpful).then(function(ok) {
        if (!ok) return;
        if (typeof window.showToast === 'function') {
          window.showToast(
            helpful === 'yes'
              ? copy.trans_thanks_for_your_feedback
              : copy.trans_feedback_will_improve,
            helpful === 'yes' ? 'success' : 'info',
            2500
          );
        }
        markDone();
      }).catch(function() {});
    });
  });
})();
})();
