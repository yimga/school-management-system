(function() {
  var btn = document.getElementById('studio-command-palette-btn');
  var backdrop = document.getElementById('studio-cmd-backdrop');
  var palette = document.getElementById('studio-cmd-palette');
  var filter = document.getElementById('studio-cmd-filter');
  var list = document.getElementById('studio-cmd-list');
  var search = document.getElementById('studio-global-search');
  if (!btn || !palette) return;
  function openPalette() {
    backdrop.classList.remove('d-none');
    palette.classList.remove('d-none');
    filter.value = '';
    filter.focus();
    filter.dispatchEvent(new Event('input'));
  }
  function closePalette() {
    backdrop.classList.add('d-none');
    palette.classList.add('d-none');
  }
  btn.addEventListener('click', openPalette);
  backdrop.addEventListener('click', closePalette);
  // Ctrl+K retired 2026-05-12 — owned by global rmc-command-palette.js. Studio
  // palette opens via #studio-command-palette-btn only; Escape still closes.
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && !palette.classList.contains('d-none')) closePalette();
  });
  filter.addEventListener('input', function() {
    var q = (this.value || '').toLowerCase();
    var items = list.querySelectorAll('li a');
    items.forEach(function(a) {
      var text = (a.textContent + ' ' + (a.getAttribute('data-keywords') || '')).toLowerCase();
      a.parentElement.style.display = text.indexOf(q) !== -1 ? '' : 'none';
    });
  });
  function getVisibleCommandLinks() {
    if (!list) return []; return Array.prototype.filter.call(list.querySelectorAll('li a'), function(el) { var li = el.closest('li'); return li && li.style.display !== 'none'; });
  }
  filter.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closePalette();
    if (e.key === 'ArrowDown' && list) { e.preventDefault(); var vis = getVisibleCommandLinks(); if (vis.length) vis[0].focus(); }
  });
  list.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closePalette();
    var a = e.target.closest('a'); if (!a) return;
    var vis = getVisibleCommandLinks(); var idx = vis.indexOf(a);
    if (e.key === 'ArrowDown' && idx >= 0 && idx < vis.length - 1) { e.preventDefault(); vis[idx + 1].focus(); }
    if (e.key === 'ArrowUp' && idx > 0) { e.preventDefault(); vis[idx - 1].focus(); }
    if (e.key === 'ArrowUp' && idx === 0) { e.preventDefault(); filter.focus(); }
    if (e.key === 'Enter') { e.preventDefault(); a.click(); }
  });
  list.addEventListener('click', function(e) {
    if (e.target.tagName === 'A') closePalette();
  });
  function trapFocus(e) {
    if (e.key !== 'Tab' || palette.classList.contains('d-none')) return;
    var focusables = palette.querySelectorAll('input, #studio-cmd-list a[href]'); if (focusables.length < 2) return;
    var first = focusables[0], last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
  palette.addEventListener('keydown', trapFocus);
  if (search && list) {
    search.addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); openPalette(); filter.value = search.value; filter.dispatchEvent(new Event('input')); }
    });
  }
})();

(function() {
  var bar = document.getElementById('studio-bottom-bar');
  if (!bar) return;
  var previewUrl = bar.getAttribute('data-preview-url') || '';
  var publishUrl = bar.getAttribute('data-publish-url') || '';
  var rollbackUrl = bar.getAttribute('data-rollback-url') || '';
  var studioMode = bar.getAttribute('data-mode') || 'experience';
  var themeForm = document.getElementById('theme-colors-form');
  var previewConfirmedField = document.getElementById('theme-preview-confirmed');
  if (themeForm && previewConfirmedField) {
    themeForm.addEventListener('input', function() { previewConfirmedField.value = '0'; });
    themeForm.addEventListener('change', function() { previewConfirmedField.value = '0'; });
  }
  function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      var cookies = document.cookie.split(';');
      for (var i = 0; i < cookies.length; i++) {
        var cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  function getCsrfToken() {
    return getCookie('csrftoken') || getCookie('rmc_manager_csrftoken') || '';
  }
  bar.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-studio-action]');
    if (!btn) return;
    var action = btn.getAttribute('data-studio-action');
    if (action === 'preview' && previewUrl) {
      var form = document.getElementById('theme-colors-form');
      if (form) {
        e.preventDefault();
        var previewConfirmed = document.getElementById('theme-preview-confirmed');
        if (previewConfirmed) previewConfirmed.value = '1';
        var fd = new FormData(form);
        fd.append('preview_section', 'theme-experience');
        fd.append('mode', studioMode);
        var csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
        fetch(previewUrl, { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrf ? csrf.value : '', 'Accept': 'application/json' }, credentials: 'same-origin' })
          .then(function(r) { return r.json().then(function(data) { return { ok: r.ok, data: data }; }); })
          .then(function(res) {
            if (res.ok && res.data.redirect_url) window.open(res.data.redirect_url, '_blank', 'noopener');
          });
      }
    } else if (action === 'publish') {
      var form = document.getElementById('theme-colors-form');
      if (form && publishUrl) {
        e.preventDefault();
        var fd = new FormData(form);
        fd.append('mode', studioMode);
        var csrf = form.querySelector('input[name="csrfmiddlewaretoken"]');
        fetch(publishUrl, { method: 'POST', body: fd, headers: { 'X-CSRFToken': csrf ? csrf.value : '', 'Accept': 'application/json' }, credentials: 'same-origin' })
          .then(function(r) { return r.json().then(function(data) { return { ok: r.ok, data: data }; }); })
          .then(function(res) {
            if (res.ok && res.data && res.data.redirect_url) window.location.href = res.data.redirect_url;
            else if (res.ok) window.location.reload();
            else if (res.data && res.data.errors && res.data.errors.length) alert(res.data.errors.join('\n'));
            else window.location.reload();
          })
          .catch(function() { window.location.reload(); });
      } else if (form) { e.preventDefault(); form.submit(); }
    } else if (action === 'rollback' && rollbackUrl) {
      e.preventDefault();
      var csrfToken = getCsrfToken();
      fetch(rollbackUrl, { method: 'POST', headers: { 'X-CSRFToken': csrfToken, 'Accept': 'application/json' }, credentials: 'same-origin' })
        .then(function(r) {
          return r.json().then(function(data) { return { ok: r.ok, data: data }; });
        })
        .then(function(res) {
          if (res.ok && res.data && res.data.redirect_url) {
            window.location.href = res.data.redirect_url;
          } else {
            window.location.reload();
          }
        })
        .catch(function() {
          window.location.reload();
        });
    }
  });
})();

// v3.54.0 (2026-05-21): Shared data-rmc-confirm handler.
// Studio OS destructive surfaces (Automation activate/replay/rollback, Control rollback,
// Launch apply, Output publish-irreversible) wire confirmation prompts by setting
// data-rmc-confirm="<message>" on the trigger element. This delegated listener fires
// before the element's own click handler / form submit / link navigation, so user
// cancellation reliably stops the action. The message is read as plain text — never
// rendered as HTML — so callers cannot inject markup through this path.
(function() {
  if (typeof document === "undefined") { return; }
  document.addEventListener("click", function(ev) {
    var target = ev.target;
    while (target && target !== document) {
      if (target.nodeType === 1 && target.hasAttribute && target.hasAttribute("data-rmc-confirm")) {
        var msg = target.getAttribute("data-rmc-confirm") || "Are you sure?";
        if (!window.confirm(msg)) {
          ev.preventDefault();
          ev.stopPropagation();
          if (typeof ev.stopImmediatePropagation === "function") {
            ev.stopImmediatePropagation();
          }
        }
        return;
      }
      target = target.parentNode;
    }
  }, true);
})();
