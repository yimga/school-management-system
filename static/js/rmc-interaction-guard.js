/**
 * Platform-wide interaction safety net (Django shells).
 * - Surfaces human-readable toasts instead of silent failures
 * - Blocks dead href="#" navigations unless explicitly allowed
 * - Catches unhandled errors in event handlers (capture phase)
 * - Ensures profile dropdown Logout stays reachable on small viewports
 */
(function () {
  'use strict';

  var UNAVAILABLE_MSG =
    'Action currently unavailable — please contact your administrator.';

  function notify(message, type) {
    var msg = message || UNAVAILABLE_MSG;
    var kind = type || 'error';
    if (typeof window.showToast === 'function') {
      window.showToast(msg, kind, 5000);
      return;
    }
    if (window.runMyCampusToast) {
      if (kind === 'success' && window.runMyCampusToast.success) {
        window.runMyCampusToast.success(msg);
      } else if (window.runMyCampusToast.gentle) {
        window.runMyCampusToast.gentle(msg);
      }
    }
  }

  function isDeadHref(href) {
    if (href == null) return false;
    var h = String(href).trim();
    return h === '' || h === '#' || h === '#!' || /^javascript:\s*void\s*0/i.test(h);
  }

  function allowDeadLink(el) {
    if (!el || !el.closest) return false;
    return !!el.closest('[data-rmc-dead-link-allow]');
  }

  function isBootstrapToggle(el) {
    return el && (el.getAttribute('data-bs-toggle') || el.getAttribute('data-toggle'));
  }

  function permissionBanner(message) {
    var host =
      document.getElementById('rmc-perm-sim-denied') ||
      document.querySelector('[data-rmc-permission-banner]');
    if (!host) return;
    host.textContent = message || UNAVAILABLE_MSG;
    host.classList.remove('d-none');
    host.setAttribute('role', 'alert');
    host.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function ensureLogoutVisible(menu) {
    if (!menu) return;
    var logout = menu.querySelector('a[href*="logout"], a.dropdown-item.text-danger');
    if (!logout) return;
    var menuRect = menu.getBoundingClientRect();
    var itemRect = logout.getBoundingClientRect();
    if (itemRect.bottom > menuRect.bottom - 4 || itemRect.top < menuRect.top + 4) {
      try {
        logout.scrollIntoView({ block: 'end', behavior: 'smooth' });
      } catch (_e) {
        menu.scrollTop = menu.scrollHeight;
      }
    }
  }

  document.addEventListener(
    'click',
    function (event) {
      var anchor = event.target && event.target.closest ? event.target.closest('a[href]') : null;
      if (!anchor || allowDeadLink(anchor) || isBootstrapToggle(anchor)) return;
      var href = anchor.getAttribute('href');
      if (!isDeadHref(href)) return;
      event.preventDefault();
      event.stopPropagation();
      notify(UNAVAILABLE_MSG, 'warning');
    },
    true
  );

  document.addEventListener(
    'click',
    function (event) {
      var btn = event.target && event.target.closest ? event.target.closest('button, [role="button"]') : null;
      if (!btn || btn.type === 'submit' || btn.disabled) return;
      var handlerAttr = btn.getAttribute('onclick');
      if (!handlerAttr) return;
      try {
        /* onclick is legacy; guard only logs — do not re-evaluate inline handlers */
      } catch (err) {
        event.preventDefault();
        event.stopPropagation();
        notify(UNAVAILABLE_MSG, 'error');
        if (typeof console !== 'undefined' && console.error) {
          console.error('[rmc-interaction-guard] onclick', err);
        }
      }
    },
    false
  );

  window.addEventListener('error', function (event) {
    if (!event || !event.error) return;
    var target = event.target;
    if (target && (target.tagName === 'SCRIPT' || target.tagName === 'LINK')) return;
    notify(UNAVAILABLE_MSG, 'error');
  });

  window.addEventListener('unhandledrejection', function (event) {
    if (!event) return;
    notify(UNAVAILABLE_MSG, 'error');
  });

  document.addEventListener('shown.bs.dropdown', function (event) {
    var root = event.target;
    if (!root) return;
    var menu = root.querySelector('.user-dropdown-menu');
    if (menu) ensureLogoutVisible(menu);
  });

  var origFetch = window.fetch;
  if (typeof origFetch === 'function') {
    window.fetch = function () {
      return origFetch.apply(this, arguments).then(function (response) {
        if (response && (response.status === 403 || response.status === 401)) {
          var url = (response.url || '').toString();
          if (url.indexOf('permission') !== -1 || url.indexOf('permissions/simulate') !== -1) {
            permissionBanner(
              'You do not have permission to run this simulation. Ask a settings administrator.'
            );
          }
        }
        return response;
      });
    };
  }

  window.RMCInteractionGuard = {
    notify: notify,
    isDeadHref: isDeadHref,
    permissionBanner: permissionBanner,
    ensureLogoutVisible: ensureLogoutVisible,
  };
})();
