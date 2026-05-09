(function() {
  var form = document.getElementById('backend-student-create-form');
  var saveBtn = document.getElementById('form-draft-save');
  var discardBtn = document.getElementById('form-draft-discard');
  if (!form) return;
  function getCookie(name) {
    var v = document.cookie.match('(?:^|; )\\s*' + name + '\\s*=\\s*([^;]+)');
    return v ? v.pop() : '';
  }
  function collectFormData() {
    var data = {};
    var inputs = form.querySelectorAll('input, select, textarea');
    for (var i = 0; i < inputs.length; i++) {
      var el = inputs[i];
      if (el.name && el.name !== 'csrfmiddlewaretoken' && el.type !== 'file') {
        if (el.type === 'checkbox' || el.type === 'radio') {
          if (el.checked) data[el.name] = el.value;
        } else {
          data[el.name] = el.value || '';
        }
      }
    }
    return data;
  }
  if (saveBtn) {
    saveBtn.addEventListener('click', function() {
      var url = saveBtn.getAttribute('data-form-draft-url');
      var payload = JSON.stringify({ data: collectFormData() });
      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
      xhr.onload = function() {
        if (xhr.status >= 200 && xhr.status < 300) {
          if (typeof window.location.reload === 'function') window.location.reload();
        }
      };
      xhr.send(payload);
    });
  }
  if (discardBtn) {
    discardBtn.addEventListener('click', function() {
      var url = discardBtn.getAttribute('data-form-draft-url');
      var xhr = new XMLHttpRequest();
      xhr.open('DELETE', url, true);
      xhr.setRequestHeader('X-CSRFToken', getCookie('csrftoken'));
      xhr.onload = function() {
        if (xhr.status === 204 || xhr.status === 200) window.location.reload();
      };
      xhr.send();
    });
  }
})();
