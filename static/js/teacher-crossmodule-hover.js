/**
 * Cross-module glass tooltip: teacher name → workload + primary room (evals compliance dashboard).
 */
(function () {
  var cache = {};
  function loadBubble(el, tid) {
    var bubble = el.querySelector('.teacher-hover-bubble');
    if (!bubble) return;
    if (cache[tid]) {
      bubble.textContent = cache[tid];
      return;
    }
    bubble.textContent = '…';
    var hoverBase = (window.RMCPlatformSurface && window.RMCPlatformSurface.url('teacher_hover')) || '';
    if (!hoverBase) return;
    var hoverSep = hoverBase.indexOf('?') >= 0 ? '&' : '?';
    fetch(hoverBase + hoverSep + 'teacher_id=' + encodeURIComponent(tid), {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) {
        return r.ok ? r.json() : Promise.reject();
      })
      .then(function (d) {
        var t =
          (d.workload_summary || '') +
          (d.primary_room && d.primary_room !== '—' ? ' · Room: ' + d.primary_room : '');
        cache[tid] = t || '—';
        bubble.textContent = cache[tid];
      })
      .catch(function () {
        bubble.textContent = 'Unable to load';
      });
  }
  document.addEventListener(
    'mouseenter',
    function (e) {
      var el = e.target.closest('.teacher-crossmodule-hover');
      if (!el) return;
      var tid = el.getAttribute('data-teacher-id');
      if (!tid) return;
      loadBubble(el, tid);
    },
    true
  );
})();
