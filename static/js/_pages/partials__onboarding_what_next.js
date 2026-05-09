(function() {
  var form = document.querySelector('.js-onboarding-dismiss-form');
  if (form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var block = document.querySelector('[data-onboarding-spotlight]');
      if (block) block.remove();
      var fd = new FormData(form);
      var token = form.querySelector('[name=csrfmiddlewaretoken]');
      if (token) fd.set('csrfmiddlewaretoken', token.value);
      fetch(form.action, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } })
        .then(function() {});
    });
  }
})();
