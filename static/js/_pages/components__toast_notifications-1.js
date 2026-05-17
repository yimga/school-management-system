(function(){
  var pageDataEl=document.getElementById("page-data-components__toast_notifications-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["components__toast_notifications-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  'use strict';
  var container = document.getElementById('toast-container');
  if (!container) return;

  var MAX_TOASTS = 5;

  // Toast function - can be called globally
  // Third arg: number = duration_ms, or object { duration: number, onUndo: function }
  window.showToast = function(message, type, durationOrOptions) {
    type = type || 'info';
    var options = typeof durationOrOptions === 'object' && durationOrOptions !== null
      ? durationOrOptions
      : { duration: durationOrOptions };
    var duration = typeof options.duration === 'number' ? options.duration : 3000;
    var onUndo = typeof options.onUndo === 'function' ? options.onUndo : null;

    // Stack limit: keep only the 5 most recent (evict oldest synchronously)
    while (container.children.length >= MAX_TOASTS && container.firstChild) {
      var oldest = container.firstChild;
      if (oldest.parentNode) oldest.parentNode.removeChild(oldest);
    }

    var toast = document.createElement('div');
    toast.className = 'toast-notification toast-' + type;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');

    var iconMap = {
      success: 'bi-check-circle-fill',
      error: 'bi-x-circle-fill',
      warning: 'bi-exclamation-triangle-fill',
      info: 'bi-info-circle-fill'
    };

    var undoHtml = onUndo
      ? '<button type="button" class="toast-undo" aria-label=((window.__RMC_PAGE_DATA__["components__toast_notifications-1"] || {})["trans_undo"])>(window.__RMC_PAGE_DATA__["components__toast_notifications-1"]||{})["trans_undo_2"]</button>'
      : '';
    toast.innerHTML =
      '<div class="toast-body">' +
        '<div class="toast-icon"><i class="bi ' + (iconMap[type] || iconMap.info) + '"></i></div>' +
        '<div class="toast-message">' + (message || '') + '</div>' +
      '</div>' +
      '<div class="toast-actions">' +
        undoHtml +
        '<button type="button" class="toast-close" aria-label=((window.__RMC_PAGE_DATA__["components__toast_notifications-1"] || {})["trans_close"])><i class="bi bi-x"></i></button>' +
      '</div>' +
      '<div class="toast-progress" role="presentation"></div>';

    var progressEl = toast.querySelector('.toast-progress');
    if (progressEl) progressEl.style.animationDuration = duration + 'ms';

    container.appendChild(toast);

    // Trigger animation
    setTimeout(function() { toast.classList.add('show'); }, 10);

    // Optional haptic feedback on success/error (mobile)
    if ((type === 'success' || type === 'error') && typeof navigator !== 'undefined' && navigator.vibrate) {
      try { navigator.vibrate(50); } catch (err) {}
    }

    // Auto-dismiss
    var timeout = setTimeout(function() {
      dismissToast(toast);
    }, duration);

    // Undo button
    var undoBtn = toast.querySelector('.toast-undo');
    if (undoBtn && onUndo) {
      undoBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        clearTimeout(timeout);
        try { onUndo(); } catch (err) {}
        dismissToast(toast);
      });
    }

    // Manual dismiss
    var closeBtn = toast.querySelector('.toast-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function() {
        clearTimeout(timeout);
        dismissToast(toast);
      });
    }

    // Click to dismiss (body/message only)
    toast.addEventListener('click', function(e) {
      if (e.target === toast || e.target.closest('.toast-body')) {
        clearTimeout(timeout);
        dismissToast(toast);
      }
    });
  };

  function dismissToast(toast) {
    var progress = toast.querySelector('.toast-progress');
    if (progress) progress.classList.add('toast-progress-paused');
    toast.classList.remove('show');
    setTimeout(function() {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 300);
  }

  // Listen for custom events
  document.addEventListener('showToast', function(e) {
    if (e.detail) {
      var d = e.detail;
      var third = d.onUndo ? { duration: d.duration || 5000, onUndo: d.onUndo } : (d.duration != null ? d.duration : undefined);
      window.showToast(d.message, d.type, third);
    }
  });
})();
})();
