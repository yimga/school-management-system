/**
 * Non-blocking toasts: success (subtle celebration) + gentle concern.
 * window.runMyCampusToast.success('Saved'); window.runMyCampusToast.gentle('Check dates');
 */
(function () {
  function ensureHost() {
    var h = document.getElementById('rmc-toast-host');
    if (!h) {
      h = document.createElement('div');
      h.id = 'rmc-toast-host';
      h.className = 'rmc-toast-host';
      h.setAttribute('aria-live', 'polite');
      document.body.appendChild(h);
    }
    return h;
  }
  function show(msg, kind) {
    var host = ensureHost();
    var el = document.createElement('div');
    el.className = 'rmc-toast rmc-toast--' + (kind || 'info');
    el.setAttribute('role', 'status');
    el.textContent = msg;
    host.appendChild(el);
    var ms = kind === 'success' ? 3200 : 4800;
    setTimeout(function () {
      el.style.opacity = '0';
      el.style.transform = 'translateY(8px)';
      el.style.transition = 'opacity 0.35s, transform 0.35s';
      setTimeout(function () {
        el.remove();
      }, 400);
    }, ms);
  }
  window.runMyCampusToast = {
    success: function (m) {
      show(m, 'success');
    },
    gentle: function (m) {
      show(m, 'gentle');
    },
    info: function (m) {
      show(m, 'info');
    },
  };
})();
