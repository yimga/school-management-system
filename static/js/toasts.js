/**
 * Minimal toast notifications (save-for-later completed).
 * Usage: window.runmycampusToast('Success message', 'success');
 */
(function () {
  function ensureContainer() {
    var id = 'runmycampus-toast-container';
    var el = document.getElementById(id);
    if (!el) {
      el = document.createElement('div');
      el.id = id;
      el.className = 'toast-container-fixed';
      document.body.appendChild(el);
    }
    return el;
  }
  function show(message, type) {
    type = type || 'info';
    var container = ensureContainer();
    var item = document.createElement('div');
    item.className = 'toast-item ' + type;
    item.textContent = message;
    container.appendChild(item);
    setTimeout(function () {
      if (item.parentNode) item.parentNode.removeChild(item);
    }, 4000);
  }
  window.runmycampusToast = show;
})();
