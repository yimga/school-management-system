  function closeAnnouncement(announcementId) {
    const element = document.getElementById('announcement-' + announcementId);
    if (element) {
      element.style.animation = 'slideDown 0.3s ease reverse';
      setTimeout(() => {
        element.remove();
      }, 300);
      
      // Optionally, store in localStorage to not show again during session
      const closedAnnouncements = JSON.parse(localStorage.getItem('closedAnnouncements') || '[]');
      if (!closedAnnouncements.includes(announcementId)) {
        closedAnnouncements.push(announcementId);
        localStorage.setItem('closedAnnouncements', JSON.stringify(closedAnnouncements));
      }
    }
  }

  // CSP: was inline onclick="closeAnnouncement(id)". This partial can be included
  // more than once per page, so bind a single delegated listener guarded by a
  // window flag to avoid double-invoking on repeat includes.
  if (!window.__rmcAnnouncementCloseBound) {
    window.__rmcAnnouncementCloseBound = true;
    document.addEventListener('click', function (e) {
      var btn = e.target && e.target.closest ? e.target.closest('[data-rmc-close-announcement]') : null;
      if (btn) {
        closeAnnouncement(btn.getAttribute('data-rmc-close-announcement'));
      }
    });
  }
