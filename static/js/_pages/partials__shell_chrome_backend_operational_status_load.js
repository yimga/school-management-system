  document.addEventListener('htmx:responseError', function(ev) {
    if (ev.detail && ev.detail.target && ev.detail.target.id === 'backend-status-fragment') {
      ev.detail.target.innerHTML = '<span class="text-muted small">-</span>';
    }
  });
