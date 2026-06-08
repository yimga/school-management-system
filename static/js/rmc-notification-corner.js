/**
 * Bottom-corner notification stack (read / snooze / dismiss).
 * Boot via window.__RMC_CORNER_NOTIFICATIONS__ or rmc:corner-notifications event.
 */
(function () {
  'use strict';

  var CORNER_ID = 'rmc-notification-corner';
  var DEFAULT_DURATION = 120000;
  var FADE_MS = 2000;

  function getContainer() {
    var el = document.getElementById(CORNER_ID);
    if (!el) {
      el = document.createElement('div');
      el.id = CORNER_ID;
      el.setAttribute('aria-live', 'polite');
      el.setAttribute('aria-atomic', 'false');
      document.body.appendChild(el);
    }
    return el;
  }

  function csrfToken() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.getAttribute('content') : '';
  }

  function postJson(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      credentials: 'same-origin',
      body: JSON.stringify(body || {}),
    }).catch(function () { return null; });
  }

  function removeNode(node) {
    if (!node || !node.parentNode) return;
    node.classList.add('is-fading');
    window.setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, FADE_MS);
  }

  function showCornerNotification(opts) {
    opts = opts || {};
    var container = getContainer();
    var duration = typeof opts.duration_ms === 'number' ? opts.duration_ms : DEFAULT_DURATION;
    var node = document.createElement('div');
    node.className = 'rmc-corner-notification rmc-corner-notification--' + (opts.type || 'info');
    node.setAttribute('role', 'alert');
    node.dataset.notificationId = opts.id || '';

    var progress = document.createElement('div');
    progress.className = 'rmc-corner-notification__progress';
    progress.style.setProperty('--rmc-corner-duration', duration + 'ms');
    node.appendChild(progress);

    var title = document.createElement('div');
    title.className = 'rmc-corner-notification__title';
    title.textContent = opts.title || '';
    node.appendChild(title);

    if (opts.message) {
      var msg = document.createElement('div');
      msg.className = 'rmc-corner-notification__message';
      msg.textContent = opts.message;
      node.appendChild(msg);
    }

    var actions = document.createElement('div');
    actions.className = 'rmc-corner-notification__actions';

    function btn(label, cls, handler) {
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn-sm ' + cls;
      b.textContent = label;
      b.addEventListener('click', function (e) {
        e.stopPropagation();
        handler();
      });
      return b;
    }

    var list = opts.actions || ['read', 'snooze', 'dismiss'];
    if (list.indexOf('read') >= 0 && opts.href) {
      actions.appendChild(btn(opts.read_label || 'Review now', 'btn-warning', function () {
        if (opts.mark_read_url) {
          postJson(opts.mark_read_url, { notification_id: opts.id });
        }
        window.location.href = opts.href;
      }));
    }
    if (list.indexOf('snooze') >= 0) {
      actions.appendChild(btn(opts.snooze_label || 'Later', 'btn-outline-secondary', function () {
        if (opts.snooze_url) postJson(opts.snooze_url, {});
        removeNode(node);
      }));
    }
    if (list.indexOf('dismiss') >= 0) {
      actions.appendChild(btn(opts.dismiss_label || 'Dismiss', 'btn-outline-secondary', function () {
        if (opts.dismiss_url) {
          postJson(opts.dismiss_url, { notification_id: opts.id });
        }
        removeNode(node);
      }));
    }
    node.appendChild(actions);
    container.appendChild(node);

    if (
      opts.browser_notify &&
      typeof Notification !== 'undefined' &&
      Notification.permission === 'granted'
    ) {
      try {
        var browserTag = 'rmc-portal-ready-' + (opts.id || 'default');
        var browserNote = new Notification(opts.title || 'RunMyCampus', {
          body: opts.message || '',
          tag: browserTag,
          icon: '/static/images/icon-192.png',
        });
        browserNote.onclick = function () {
          window.focus();
          if (opts.href) window.location.href = opts.href;
          browserNote.close();
        };
      } catch (_browserErr) {
        /* local Notification is best-effort */
      }
    }

    window.requestAnimationFrame(function () {
      node.classList.add('is-visible');
    });

    var dismissTimer = window.setTimeout(function () {
      node.classList.add('is-fading');
      window.setTimeout(function () {
        removeNode(node);
      }, FADE_MS);
    }, duration);

    node.addEventListener('mouseenter', function () {
      node.classList.remove('is-fading');
    });
    node.addEventListener('mouseleave', function () {
      /* no-op: timer still runs */
    });

    return {
      dismiss: function () {
        window.clearTimeout(dismissTimer);
        removeNode(node);
      },
    };
  }

  window.showCornerNotification = showCornerNotification;

  function boot(list) {
    if (!list || !list.length) return;
    list.forEach(function (item) {
      showCornerNotification(item);
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    if (window.__RMC_CORNER_NOTIFICATIONS__) {
      boot(window.__RMC_CORNER_NOTIFICATIONS__);
    }
  });

  document.addEventListener('rmc:corner-notifications', function (e) {
    if (e.detail) boot(e.detail);
  });
})();
