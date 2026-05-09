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
