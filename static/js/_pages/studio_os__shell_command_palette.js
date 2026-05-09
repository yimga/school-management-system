// Studio OS shell command palette: Ctrl+K toggles, filter, keyboard nav,
// focus trap. Pure JS — no Django context needed.
// Externalised from templates/studio_os/partials/shell_main_content.html
// (where the inline block was unterminated — fixed here with a proper IIFE).
(function () {
  var btn = document.getElementById('studio-command-palette-btn');
  var backdrop = document.getElementById('studio-cmd-backdrop');
  var palette = document.getElementById('studio-cmd-palette');
  var filter = document.getElementById('studio-cmd-filter');
  var list = document.getElementById('studio-cmd-list');
  // var search = document.getElementById('studio-global-search'); // reserved
  if (!btn || !palette) return;

  function openPalette() {
    if (backdrop) backdrop.classList.remove('d-none');
    palette.classList.remove('d-none');
    if (filter) {
      filter.value = '';
      filter.focus();
      filter.dispatchEvent(new Event('input'));
    }
  }
  function closePalette() {
    if (backdrop) backdrop.classList.add('d-none');
    palette.classList.add('d-none');
  }

  btn.addEventListener('click', openPalette);
  if (backdrop) backdrop.addEventListener('click', closePalette);

  document.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
      e.preventDefault();
      openPalette();
    }
    if (e.key === 'Escape' && !palette.classList.contains('d-none')) closePalette();
  });

  if (filter) {
    filter.addEventListener('input', function () {
      var q = (this.value || '').toLowerCase();
      if (!list) return;
      var items = list.querySelectorAll('li a');
      items.forEach(function (a) {
        var text = (a.textContent + ' ' + (a.getAttribute('data-keywords') || '')).toLowerCase();
        a.parentElement.style.display = text.indexOf(q) !== -1 ? '' : 'none';
      });
    });
  }

  function getVisibleCommandLinks() {
    if (!list) return [];
    return Array.prototype.filter.call(
      list.querySelectorAll('li a'),
      function (el) { var li = el.closest('li'); return li && li.style.display !== 'none'; }
    );
  }

  if (filter) {
    filter.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closePalette();
      if (e.key === 'ArrowDown' && list) {
        e.preventDefault();
        var vis = getVisibleCommandLinks();
        if (vis.length) vis[0].focus();
      }
    });
  }

  if (list) {
    list.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closePalette();
      var a = e.target.closest('a'); if (!a) return;
      var vis = getVisibleCommandLinks();
      var idx = vis.indexOf(a);
      if (e.key === 'ArrowDown' && idx >= 0 && idx < vis.length - 1) {
        e.preventDefault(); vis[idx + 1].focus();
      }
      if (e.key === 'ArrowUp' && idx > 0) {
        e.preventDefault(); vis[idx - 1].focus();
      }
      if (e.key === 'ArrowUp' && idx === 0 && filter) {
        e.preventDefault(); filter.focus();
      }
      if (e.key === 'Enter') {
        e.preventDefault(); a.click();
      }
    });
    list.addEventListener('click', function (e) {
      if (e.target.tagName === 'A') closePalette();
    });
  }

  // Focus trap inside the open palette.
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Tab' || palette.classList.contains('d-none')) return;
    var focusables = palette.querySelectorAll('input, #studio-cmd-list a[href]');
    if (focusables.length < 2) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault(); last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault(); first.focus();
    }
  });
})();
