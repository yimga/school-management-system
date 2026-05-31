(function(){
  var pageDataEl=document.getElementById("page-data-components__toast_notifications-1");
  window.__RMC_PAGE_DATA__=window.__RMC_PAGE_DATA__||{};
  if(pageDataEl){try{window.__RMC_PAGE_DATA__["components__toast_notifications-1"]=JSON.parse(pageDataEl.textContent||"{}")}catch(_e){}}
(function() {
  'use strict';
  var container = document.getElementById('toast-container');
  if (!container) return;

  var MAX_TOASTS = 5;

  // v4.00.25 (2026-05-29) — Toast routing contract.
  // Per UX directive, bottom-of-screen toasts are suppressed in favor of
  // the in-app notifications page. showToast() now:
  //   1) Suppresses the visual toast (no DOM render in the corner).
  //   2) POSTs the payload to /api/v1/notifications/self-capture/ so the
  //      message persists as a Notification record the user can see in
  //      /accounts/notifications/.
  //   3) Pulses the header bell + bumps its unread badge to draw the eye.
  //   4) Honors `onUndo` callbacks for backwards compat (rare path: we
  //      still render an inline ephemeral chip for these so the user can
  //      undo).
  // Pages that genuinely need the legacy bottom-corner UX can opt in by
  // setting window.__RMC_TOAST_LEGACY_VISUAL__ = true before showToast
  // runs (no callers do today; flag exists as an escape hatch).

  function getCsrfToken() {
    var v = (document.cookie || '').match(/csrftoken=([^;]+)/);
    if (v) return v[1];
    var m = document.querySelector('meta[name="csrf-token"]');
    if (m && m.content) return m.content;
    var inp = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return inp ? inp.value : '';
  }

  function persistToInbox(message, type, opts) {
    try {
      var captureUrl = (window.RMCPlatformSurface && window.RMCPlatformSurface.url('notifications_self_capture')) || '';
      if (!captureUrl) return;
      fetch(captureUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify({
          title: (opts && opts.title) || '',
          message: String(message || ''),
          type: type || 'info',
          link: (opts && opts.link) || ''
        })
      }).then(function () { bumpBellBadge(type); }).catch(function () {});
    } catch (e) {}
  }

  function bumpBellBadge(type) {
    var bells = document.querySelectorAll('.cp-topbar-bell, [data-rmc-header-bell]');
    bells.forEach(function (b) {
      var badge = b.querySelector('.cp-topbar-bell__badge, .topbar-icon-badge');
      if (badge) {
        var n = parseInt(badge.textContent, 10);
        badge.textContent = String((isNaN(n) ? 0 : n) + 1);
        badge.style.display = '';
      } else {
        var newBadge = document.createElement('span');
        newBadge.className = 'cp-topbar-bell__badge';
        newBadge.textContent = '1';
        b.appendChild(newBadge);
      }
      b.classList.add('rmc-bell-pulse');
      setTimeout(function () { b.classList.remove('rmc-bell-pulse'); }, 1400);
    });
  }

  // Toast function - can be called globally
  // Third arg: number = duration_ms, or object { duration: number, onUndo: function }
  window.showToast = function(message, type, durationOrOptions) {
    type = type || 'info';
    var options = typeof durationOrOptions === 'object' && durationOrOptions !== null
      ? durationOrOptions
      : { duration: durationOrOptions };
    var duration = typeof options.duration === 'number' ? options.duration : 3000;
    var onUndo = typeof options.onUndo === 'function' ? options.onUndo : null;

    // Route to inbox + pulse the bell. Always happens regardless of visual mode.
    persistToInbox(message, type, options);

    // Legacy visual path: only render the bottom-corner toast when an
    // onUndo handler is supplied (needs a UI to click) OR the page has
    // explicitly opted into the legacy visual.
    var allowVisual = !!onUndo || !!window.__RMC_TOAST_LEGACY_VISUAL__;
    if (!allowVisual) return;

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
