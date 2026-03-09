/**
 * Return-to-origin: when you open a form/page from anywhere, Cancel/Close brings you back.
 * Stores the current URL on list/dashboard pages; Back/Cancel use it so users never lose context.
 * Forward-thinking: works across admin, /super/, and portal; survives cross-navigation.
 */
(function () {
  var KEY = 'runmycampus-return-url';
  var SUPER_PREFIX = '/super/';
  var ADMIN_PREFIX = '/admin/';

  function isSameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  function isListOrDashboardPage(pathname) {
    if (!pathname) return false;
    if (pathname === '/super' || pathname === '/super/' || pathname.indexOf(SUPER_PREFIX) === 0) {
      if (pathname.indexOf('/add') !== -1 || pathname.indexOf('/create') !== -1) return false;
      if (/\/[0-9a-f-]{36}\//.test(pathname)) return false;
      return true;
    }
    if (pathname.indexOf(ADMIN_PREFIX) === 0) {
      if (pathname.indexOf('/add/') !== -1) return false;
      if (/\/[^/]+\/change\/$/.test(pathname)) return false;
      return true;
    }
    /* Tenant portal/backend list or dashboard (not add/form pages) */
    if (pathname.indexOf('/accounts/backend') === 0 || pathname.indexOf('/portal/') === 0 ||
        pathname.indexOf('/finance/') === 0 || pathname.indexOf('/evals/') === 0 ||
        pathname.indexOf('/payroll/') === 0 || pathname.indexOf('/analytics/') === 0 ||
        pathname.indexOf('/compliance/') === 0 || pathname.indexOf('/requests/') === 0) {
      if (pathname.indexOf('/add') !== -1 || pathname.indexOf('/create') !== -1 || pathname.indexOf('/edit') !== -1) return false;
      return true;
    }
    return false;
  }

  function getStored() {
    try {
      var u = sessionStorage.getItem(KEY);
      return u && isSameOrigin(u) ? u : null;
    } catch (e) {
      return null;
    }
  }

  function setStored(url) {
    try {
      if (url && isSameOrigin(url)) sessionStorage.setItem(KEY, url);
    } catch (e) {}
  }

  function applyToBackButtons() {
    document.querySelectorAll('.js-return-to-origin, [data-return-to-origin]').forEach(function (el) {
      if (el.dataset.returnToOriginBound) return;
      el.dataset.returnToOriginBound = '1';
      var fallback = el.getAttribute('data-fallback') || (window.location.pathname.indexOf(ADMIN_PREFIX) === 0 ? '/admin/' : '/super/');
      var stored = getStored();
      var ref = document.referrer;
      var href = (stored && isSameOrigin(stored)) ? stored : (ref && isSameOrigin(ref) ? ref : fallback);
      if (el.tagName.toLowerCase() === 'a') el.setAttribute('href', href);
      el.addEventListener('click', function (e) {
        if (el.tagName.toLowerCase() !== 'a' || el.getAttribute('href') === '#') {
          e.preventDefault();
          window.location.href = href;
        }
      });
    });
  }

  function init() {
    var path = window.location.pathname || '';
    if (isListOrDashboardPage(path)) setStored(window.location.href);
    applyToBackButtons();
  }

  /* Keyboard: Escape goes back when not in input and no modal open */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || e.ctrlKey || e.metaKey || e.altKey) return;
    var tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : '';
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
    var modal = document.querySelector('.modal.show, [role="dialog"][aria-modal="true"]');
    if (modal) return;
    var url = getStored() || (document.referrer && isSameOrigin(document.referrer) ? document.referrer : (window.location.pathname.indexOf(ADMIN_PREFIX) === 0 ? '/admin/' : '/super/'));
    if (url && url !== window.location.href) {
      e.preventDefault();
      window.location.href = url;
    }
  });

  /* Focus: when modal opens focus first focusable; when it closes restore focus to trigger */
  document.addEventListener('shown.bs.modal', function (e) {
    var modal = e.target;
    var first = modal.querySelector('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
    if (first) first.focus();
  });
  document.addEventListener('hidden.bs.modal', function (e) {
    var trigger = document.querySelector('[data-bs-toggle="modal"][data-bs-target="#' + e.target.id + '"]');
    if (trigger) trigger.focus();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  window.getReturnToOriginUrl = function (fallback) {
    return getStored() || (document.referrer && isSameOrigin(document.referrer) ? document.referrer : (fallback || '/super/'));
  };
  window.setReturnToOriginUrl = setStored;
})();
