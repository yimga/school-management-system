/**
 * Inline quarterly security posture banner — snooze (session) + optional collapse memory.
 */
(function () {
  'use strict';

  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  }

  function postSnooze(url) {
    if (!url) return Promise.resolve(null);
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'same-origin',
      body: '{}',
    }).catch(function () {
      return null;
    });
  }

  function snoozeUrl() {
    var cfg = document.getElementById('rmc-security-posture-snooze-config');
    if (!cfg) return '';
    try {
      return JSON.parse(cfg.textContent || '{}').snooze_url || '';
    } catch (e) {
      return '';
    }
  }

  document.querySelectorAll('[data-rmc-security-posture-snooze="1"]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      postSnooze(snoozeUrl()).then(function () {
        document.querySelectorAll('[data-rmc-security-posture-banner="1"]').forEach(function (el) {
          if (el.parentNode) el.parentNode.removeChild(el);
        });
      });
    });
  });

  document.querySelectorAll('[data-rmc-security-posture-banner="1"]').forEach(function (details) {
    var key = 'rmc-security-posture-collapsed';
    try {
      if (window.sessionStorage.getItem(key) === '1') {
        details.removeAttribute('open');
      }
      details.addEventListener('toggle', function () {
        window.sessionStorage.setItem(key, details.open ? '0' : '1');
      });
    } catch (e) {
      /* sessionStorage unavailable — collapsible still works per navigation */
    }
  });
})();
