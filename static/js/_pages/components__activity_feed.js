// Activity Feed JavaScript
class ActivityFeed {
  constructor() {
    this.page = 1;
    this.filter = '';
    this.init();
  }

  init() {
    this.setupEventListeners();
    this.loadActivities();
  }

  setupEventListeners() {
    const filterSelect = document.getElementById('activityFilterType');
    const refreshBtn = document.getElementById('activityRefreshBtn');
    const loadMoreBtn = document.getElementById('activityLoadMoreBtn');

    if (filterSelect) {
      filterSelect.addEventListener('change', (e) => {
        this.filter = e.target.value;
        this.page = 1;
        this.loadActivities();
      });
    }

    if (refreshBtn) {
      refreshBtn.addEventListener('click', () => {
        this.page = 1;
        this.loadActivities();
      });
    }

    if (loadMoreBtn) {
      loadMoreBtn.addEventListener('click', () => {
        this.page++;
        this.loadActivities(true);
      });
    }
  }

  async loadActivities(append = false) {
    const list = document.getElementById('activityList');
    if (!list) return;

    if (!append) {
      list.innerHTML = '<div class="activity-loading"><i class="fas fa-spinner fa-spin"></i> Loading activities...</div>';
    }

    try {
      const url = `/api/activities/?page=${this.page}${this.filter ? '&filter=' + this.filter : ''}`;
      const response = await fetch(url);
      
      if (!response.ok) {
        throw new Error('Failed to load activities');
      }

      const data = await response.json();
      this.renderActivities(data.activities, append);
    } catch (error) {
      console.error('Error loading activities:', error);
      if (!append) {
        list.innerHTML = '<div class="activity-empty">No activities available</div>';
      }
    }
  }

  renderActivities(activities, append = false) {
    const list = document.getElementById('activityList');
    if (!list) return;

    if (!append) {
      list.innerHTML = '';
    }

    if (!activities || activities.length === 0) {
      if (!append) {
        list.innerHTML = '<div class="activity-empty">No activities to display</div>';
      }
      return;
    }

    activities.forEach(activity => {
      const item = document.createElement('div');
      item.className = 'activity-item';
      item.innerHTML = `
        <div class="activity-icon ${activity.type}">
          <i class="${this.getIconClass(activity.type)}"></i>
        </div>
        <div class="activity-content">
          <p class="activity-title">${this.escapeHtml(activity.title)}</p>
          <p class="activity-description">${this.escapeHtml(activity.description)}</p>
          <div class="activity-meta">
            <span class="activity-timestamp">
              <i class="fas fa-clock"></i> ${this.formatTime(activity.timestamp)}
            </span>
            ${activity.user ? `<span class="activity-user"><i class="fas fa-user"></i> ${this.escapeHtml(activity.user)}</span>` : ''}
            ${activity.type ? `<span class="activity-badge">${this.formatType(activity.type)}</span>` : ''}
          </div>
        </div>
      `;
      list.appendChild(item);
    });
  }

  getIconClass(type) {
    const icons = {
      admin: 'fas fa-shield-alt',
      student: 'fas fa-user-graduate',
      system: 'fas fa-cog',
      enrollment: 'fas fa-door-open'
    };
    return icons[type] || 'fas fa-circle';
  }

  formatType(type) {
    const types = {
      admin: 'Admin Action',
      student: 'Student Change',
      system: 'System Event',
      enrollment: 'Enrollment'
    };
    return types[type] || type;
  }

  formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleDateString();
  }

  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Initialize when ready
document.addEventListener('DOMContentLoaded', () => {
  window.activityFeed = new ActivityFeed();
  console.log('✅ Activity Feed initialized');
});
