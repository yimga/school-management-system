document.addEventListener('DOMContentLoaded', function() {
  // Auto-refresh timestamp every minute
  setInterval(function() {
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    const timeEl = document.querySelector('.last-updated');
    if (timeEl) {
      timeEl.textContent = `Last updated: ${timeString}`;
    }
  }, 60000);

  // Filter button handlers
  const filterBtns = document.querySelectorAll('.filter-btn');
  filterBtns.forEach(btn => {
    btn.addEventListener('click', function() {
      filterBtns.forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      const filter = this.getAttribute('data-filter');
      // Emit custom event for dashboard to handle
      document.dispatchEvent(new CustomEvent('dashboard-filter-change', { detail: { filter } }));
    });
  });
});
