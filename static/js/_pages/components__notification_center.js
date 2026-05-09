document.addEventListener('DOMContentLoaded', function() {
  const notificationBell = document.getElementById('notificationBell');
  const notificationBadge = document.getElementById('notificationBadge');
  const notificationBody = document.getElementById('notificationBody');
  const notificationTabs = document.querySelectorAll('.notification-tab');
  const markAllReadBtn = document.getElementById('markAllRead');
  
  let currentTab = 'all';
  let notifications = [];

  // Fetch notifications from API
  async function fetchNotifications() {
    try {
      const response = await fetch('/api/notifications/');
      const data = await response.json();
      notifications = data.notifications || [];
      updateBadgeCount();
      renderNotifications();
    } catch (error) {
      console.error('Error fetching notifications:', error);
      renderError();
    }
  }

  // Render notifications based on current tab
  function renderNotifications() {
    const filteredNotifications = currentTab === 'all' 
      ? notifications 
      : notifications.filter(n => n.type === currentTab.slice(0, -1));

    if (filteredNotifications.length === 0) {
      notificationBody.innerHTML = `
        <div class="notification-empty">
          <i class="bi bi-inbox"></i>
          <p class="mb-0">No notifications</p>
        </div>
      `;
      return;
    }

    notificationBody.innerHTML = filteredNotifications.map(notification => `
      <div class="notification-item ${notification.is_read ? '' : 'unread'}" data-id="${notification.id}">
        <div class="notification-content">
          <div class="notification-icon ${notification.type}">
            <i class="bi ${getIconForType(notification.type)}"></i>
          </div>
          <div class="notification-details">
            <div class="notification-title">${notification.title}</div>
            <div class="notification-message">${notification.message}</div>
            <div class="notification-meta">
              <span class="notification-time">
                <i class="bi bi-clock"></i>
                ${formatTime(notification.created_at)}
              </span>
              <span class="notification-category">${notification.category}</span>
            </div>
          </div>
        </div>
      </div>
    `).join('');

    // Add click handlers to notification items
    document.querySelectorAll('.notification-item').forEach(item => {
      item.addEventListener('click', function() {
        const notificationId = this.dataset.id;
        markAsRead(notificationId);
        // Navigate to notification link if available
        const notification = notifications.find(n => n.id == notificationId);
        if (notification && notification.link) {
          window.location.href = notification.link;
        }
      });
    });
  }

  // Render error state
  function renderError() {
    notificationBody.innerHTML = `
      <div class="notification-empty">
        <i class="bi bi-exclamation-triangle"></i>
        <p class="mb-0">Failed to load notifications</p>
        <button type="button" class="btn btn-sm btn-primary mt-2" onclick="location.reload()">Retry</button>
      </div>
    `;
  }

  // Get icon for notification type
  function getIconForType(type) {
    const icons = {
      message: 'bi-envelope',
      task: 'bi-clipboard-check',
      alert: 'bi-exclamation-circle',
      success: 'bi-check-circle',
    };
    return icons[type] || 'bi-bell';
  }

  // Format time ago. Uses Intl.RelativeTimeFormat (locale-aware) when available;
  // falls back to short English strings otherwise.
  const NOTIF_LOCALE = (document.documentElement.lang || navigator.language || 'en');
  let _RTF = null;
  try {
    _RTF = new Intl.RelativeTimeFormat(NOTIF_LOCALE, { numeric: 'auto', style: 'short' });
  } catch (_e) { _RTF = null; }

  function formatTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);

    if (_RTF) {
      if (diffInSeconds < 60) return _RTF.format(-diffInSeconds, 'second');
      if (diffInSeconds < 3600) return _RTF.format(-Math.floor(diffInSeconds / 60), 'minute');
      if (diffInSeconds < 86400) return _RTF.format(-Math.floor(diffInSeconds / 3600), 'hour');
      if (diffInSeconds < 604800) return _RTF.format(-Math.floor(diffInSeconds / 86400), 'day');
      return date.toLocaleDateString(NOTIF_LOCALE);
    }
    // Fallback (very old browsers / Intl unavailable)
    if (diffInSeconds < 60) return 'Just now';
    if (diffInSeconds < 3600) return `${Math.floor(diffInSeconds / 60)}m ago`;
    if (diffInSeconds < 86400) return `${Math.floor(diffInSeconds / 3600)}h ago`;
    if (diffInSeconds < 604800) return `${Math.floor(diffInSeconds / 86400)}d ago`;
    return date.toLocaleDateString();
  }

  // Update badge count
  function updateBadgeCount() {
    const unreadCount = notifications.filter(n => !n.is_read).length;
    notificationBadge.textContent = unreadCount > 99 ? '99+' : unreadCount;
  }

  // Mark notification as read
  async function markAsRead(notificationId) {
    try {
      await fetch(`/api/notifications/${notificationId}/read/`, {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
        },
      });
      
      // Update local state
      const notification = notifications.find(n => n.id == notificationId);
      if (notification) {
        notification.is_read = true;
        updateBadgeCount();
        renderNotifications();
      }
    } catch (error) {
      console.error('Error marking notification as read:', error);
    }
  }

  // Mark all notifications as read
  markAllReadBtn.addEventListener('click', async function() {
    try {
      await fetch('/api/notifications/mark-all-read/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCookie('csrftoken'),
        },
      });
      
      notifications.forEach(n => n.is_read = true);
      updateBadgeCount();
      renderNotifications();
    } catch (error) {
      console.error('Error marking all as read:', error);
    }
  });

  // Tab switching
  notificationTabs.forEach(tab => {
    tab.addEventListener('click', function() {
      notificationTabs.forEach(t => t.classList.remove('active'));
      this.classList.add('active');
      currentTab = this.dataset.tab;
      renderNotifications();
    });
  });

  // Get CSRF token
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === (name + '=')) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  // Initial load
  fetchNotifications();

  // Refresh notifications every 30 seconds
  setInterval(fetchNotifications, 30000);

  // Listen for new notification events (WebSocket or polling)
  document.addEventListener('new-notification', function(e) {
    notifications.unshift(e.detail);
    updateBadgeCount();
    if (currentTab === 'all' || currentTab === e.detail.type + 's') {
      renderNotifications();
    }
    
    // Show toast notification
    showToast(e.detail);
  });

  // Show toast notification
  function showToast(notification) {
    const toast = document.createElement('div');
    toast.className = 'notification-toast';
    // Assistive-tech: announce immediately, do not interrupt other live regions.
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    toast.innerHTML = `
      <div class="notification-icon ${notification.type}" aria-hidden="true">
        <i class="bi ${getIconForType(notification.type)}"></i>
      </div>
      <div class="notification-toast-content">
        <div class="notification-toast-title">${notification.title}</div>
        <div class="notification-toast-message">${notification.message}</div>
      </div>
    `;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('show'), 100);
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 5000);
  }
});
