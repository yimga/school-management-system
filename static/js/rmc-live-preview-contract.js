(function () {
  function qs(root, selector) {
    return root ? root.querySelector(selector) : null;
  }

  function setFallback(root, visible, reason) {
    var panel = qs(root, '[data-rmc-preview-fallbacks]');
    var status = qs(root, '[data-rmc-preview-status]');
    if (panel) panel.hidden = !visible;
    if (status && reason) status.textContent = reason;
    root.setAttribute('data-rmc-preview-state', visible ? 'fallback' : 'live');
  }

  function setCramped(root, cramped) {
    root.setAttribute('data-rmc-preview-space', cramped ? 'cramped' : 'spacious');
    if (cramped) {
      setFallback(root, true, root.getAttribute('data-preview-cramped-label') || 'Inline preview is too narrow. Use modal, popout, or new tab.');
    }
  }

  function setFrameUrl(root, url) {
    var frame = qs(root, 'iframe[data-rmc-preview-frame]');
    if (!frame || !url) return;
    setFallback(root, false, root.getAttribute('data-preview-loading-label') || 'Rendering live preview');
    frame.dataset.loaded = '0';
    frame.src = url;
  }

  function openModal(root) {
    var frame = qs(root, 'iframe[data-rmc-preview-frame]');
    var url = frame && frame.src;
    if (!url || !window.bootstrap) {
      if (url) window.open(url, '_blank', 'noopener,noreferrer');
      return;
    }
    var modal = document.getElementById('rmc-live-preview-modal');
    if (!modal) return;
    var modalFrame = qs(modal, '[data-rmc-live-preview-modal-frame]');
    if (modalFrame) modalFrame.src = url;
    window.bootstrap.Modal.getOrCreateInstance(modal).show();
  }

  function init(root) {
    var frame = qs(root, 'iframe[data-rmc-preview-frame]');
    var roleSelect = qs(root, '[data-rmc-preview-role]');
    var deviceSelect = qs(root, '[data-rmc-preview-device]');
    var retry = qs(root, '[data-rmc-preview-retry]');
    var modalBtn = qs(root, '[data-rmc-preview-modal]');
    var popoutBtn = qs(root, '[data-rmc-preview-popout]');
    var newTab = qs(root, '[data-rmc-preview-new-tab]');
    var frameShell = qs(root, '[data-rmc-preview-frame-shell]');
    var timeoutMs = parseInt(root.getAttribute('data-preview-timeout-ms') || '8000', 10);
    var minInlineWidth = parseInt(root.getAttribute('data-preview-min-inline-width') || '720', 10);
    var timer = null;

    function currentUrl() {
      return (roleSelect && roleSelect.value) || (frame && frame.src) || '';
    }

    function syncLinks() {
      var url = currentUrl();
      if (newTab) newTab.href = url || '#';
      if (popoutBtn) popoutBtn.disabled = !url;
      if (modalBtn) modalBtn.disabled = !url;
    }

    function armTimeout() {
      window.clearTimeout(timer);
      if (!frame) return;
      timer = window.setTimeout(function () {
        if (frame.dataset.loaded !== '1') {
          setFallback(root, true, root.getAttribute('data-preview-timeout-label') || 'Inline preview is taking too long. Use a fallback view.');
        }
      }, timeoutMs);
    }

    if (frame) {
      frame.addEventListener('load', function () {
        frame.dataset.loaded = '1';
        window.clearTimeout(timer);
        setFallback(root, false, root.getAttribute('data-preview-live-label') || 'Live preview rendered');
        syncLinks();
        measureInlineSpace();
      });
      frame.addEventListener('error', function () {
        setFallback(root, true, root.getAttribute('data-preview-error-label') || 'Inline preview was blocked. Use a fallback view.');
      });
      armTimeout();
    }

    if (roleSelect) {
      roleSelect.addEventListener('change', function () {
        setFrameUrl(root, roleSelect.value);
        syncLinks();
        armTimeout();
      });
    }

    if (deviceSelect && frameShell) {
      deviceSelect.addEventListener('change', function () {
        frameShell.setAttribute('data-preview-device', deviceSelect.value || 'desktop');
        window.setTimeout(measureInlineSpace, 0);
      });
    }

    if (retry) {
      retry.addEventListener('click', function () {
        var url = currentUrl();
        if (frame && url) {
          frame.dataset.loaded = '0';
          frame.src = url;
          armTimeout();
        }
      });
    }

    if (modalBtn) modalBtn.addEventListener('click', function () { openModal(root); });
    if (popoutBtn) {
      popoutBtn.addEventListener('click', function () {
        var url = currentUrl();
        if (url) window.open(url, 'rmc-live-preview', 'popup,width=1280,height=900');
      });
    }

    function measureInlineSpace() {
      var box = frameShell || qs(root, '[data-rmc-preview-frame-shell]');
      if (!box) return;
      var device = box.getAttribute('data-preview-device') || 'desktop';
      var cramped = device === 'desktop' && box.getBoundingClientRect().width < minInlineWidth;
      setCramped(root, cramped);
    }

    if (frameShell) {
      if ('ResizeObserver' in window) {
        var ro = new ResizeObserver(measureInlineSpace);
        ro.observe(frameShell);
      } else {
        window.addEventListener('resize', measureInlineSpace);
      }
      measureInlineSpace();
    }

    syncLinks();
  }

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-rmc-live-preview-contract]').forEach(init);
  });
})();
