(function(){
  var pageDataEl=document.getElementById("page-data-components__live_preview_button-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["components__live_preview_button-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var btn = document.querySelector('.live-preview-platform-btn:not([data-bound])');
  if (!btn) return;
  btn.setAttribute('data-bound', '1');
  var formId = btn.getAttribute('data-form-id');
  var form = formId ? document.getElementById(formId) : btn.closest('form');
  var keepCheckbox = btn.closest('.live-preview-platform-wrapper').querySelector('.live-preview-keep');
  if (!form) return;
  btn.addEventListener('click', function() {
    var fd = new FormData(form);
    fd.append('preview_section', btn.getAttribute('data-preview-section') || '');
    if (keepCheckbox && keepCheckbox.checked) fd.append('preview_keep', '1');
    var csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
    var url = '(window.__RMC_PAGE_DATA__["components__live_preview_button-1"]||{})["url_siteconfig_preview_from_form"]';
    fetch(url, { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrf ? csrf.value : '', 'Accept': 'application/json' }, credentials: 'same-origin' })
      .then(function(r) { return r.json().then(function(data) { return { ok: r.ok, data: data }; }); })
      .then(function(res) {
        if (!res.ok) {
          var msg = (res.data.errors && res.data.errors.length) ? res.data.errors.join(' ') : '(window.__RMC_PAGE_DATA__["components__live_preview_button-1"]||{})["trans_preview_failed"]';
          if (typeof window.showToast === 'function') window.showToast(msg, 'error', 4000);
          return;
        }
        if (res.data.redirect_url) window.open(res.data.redirect_url, '_blank', 'noopener');
        if (typeof window.showToast === 'function') window.showToast('(window.__RMC_PAGE_DATA__["components__live_preview_button-1"]||{})["trans_preview_opened_in_new_tab"]', 'success', 2000);
      })
      .catch(function() {
        if (typeof window.showToast === 'function') window.showToast('(window.__RMC_PAGE_DATA__["components__live_preview_button-1"]||{})["trans_preview_failed_2"]', 'error', 3000);
      });
  });
})();
})();
