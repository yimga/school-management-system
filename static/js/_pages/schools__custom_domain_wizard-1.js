(function(){
  var pageDataEl=document.getElementById("page-data-schools__custom_domain_wizard-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["schools__custom_domain_wizard-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  var form = document.getElementById('domain-form');
  var errorEl = document.getElementById('domain-error');
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var fd = new FormData(form);
      var domain = fd.get('domain');
      errorEl.style.display = 'none';
      fetch('(window.__RMC_PAGE_DATA__["schools__custom_domain_wizard-1"]||{})["url_api_domains_list_or_create"]', {
        method: 'POST',
        body: JSON.stringify({ domain: domain }),
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
          'Accept': 'application/json'
        },
        credentials: 'same-origin'
      }).then(function(r) {
        if (r.ok) { window.location.reload(); return; }
        return r.json().then(function(d) { throw d; });
      }).catch(function(err) {
        errorEl.textContent = err && err.error ? err.error : '(window.__RMC_PAGE_DATA__["schools__custom_domain_wizard-1"]||{})["trans_request_failed"]';
        errorEl.style.display = 'block';
      });
    });
  }
  document.querySelectorAll('.copy-txt').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var t = this.getAttribute('data-txt');
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(t);
      }
    });
  });
  document.querySelectorAll('.verify-btn').forEach(function(btn) {
    btn.addEventListener('click', function() {
      var id = this.getAttribute('data-id');
      var self = this;
      self.disabled = true;
      fetch('(window.__RMC_PAGE_DATA__["schools__custom_domain_wizard-1"]||{})["var_api_domains_url_default_api_tenant_domains"]'.replace(/\/$/, '') + '/' + id + '/verify/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value,
          'Accept': 'application/json',
          'Content-Type': 'application/x-www-form-urlencoded'
        },
        credentials: 'same-origin',
        body: 'csrfmiddlewaretoken=' + encodeURIComponent(document.querySelector('[name=csrfmiddlewaretoken]').value)
      }).then(function(r) {
        return r.json();
      }).then(function() {
        window.location.reload();
      }).finally(function() {
        self.disabled = false;
      });
    });
  });
})();
})();
