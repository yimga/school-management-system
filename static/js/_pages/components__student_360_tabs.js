// Student 360 Tab Functionality
class Student360 {
  constructor() {
    this.studentId = null;
    this.init();
  }

  init() {
    this.setupEventListeners();
  }

  setupEventListeners() {
    const closeBtn = document.getElementById('closeStudent360');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.close());
    }
  }

  show(studentId) {
    this.studentId = studentId;
    const container = document.getElementById('student360Container');
    if (container) {
      container.style.display = 'block';
      this.loadStudentData(studentId);
    }
  }

  close() {
    const container = document.getElementById('student360Container');
    if (container) {
      container.style.display = 'none';
    }
  }

  async loadStudentData(studentId) {
    this.setPanelState('academicPerformance', 'loading', 'Loading academic details...');
    this.setPanelState('feeStatus', 'loading', 'Loading finance details...');
    this.setPanelState('participationStats', 'loading', 'Loading engagement details...');
    this.setPanelState('documentsList', 'loading', 'Loading documents...');
    try {
      const response = await fetch(`/api/students/${studentId}/`);
      if (response.ok) {
        const data = await response.json();
        this.renderStudentData(data);
      } else {
        this.setPanelState('academicPerformance', 'error', 'Unable to load student data right now.');
        this.setPanelState('feeStatus', 'error', 'Finance details are unavailable.');
        this.setPanelState('participationStats', 'error', 'Engagement details are unavailable.');
        this.setPanelState('documentsList', 'error', 'Documents are unavailable.');
      }
    } catch (error) {
      this.setPanelState('academicPerformance', 'error', 'Unable to load student data right now.');
      this.setPanelState('feeStatus', 'error', 'Finance details are unavailable.');
      this.setPanelState('participationStats', 'error', 'Engagement details are unavailable.');
      this.setPanelState('documentsList', 'error', 'Documents are unavailable.');
    }
  }

  renderStudentData(data) {
    // Update header
    document.getElementById('studentName').textContent = data.name || 'Student';
    document.getElementById('studentClass').textContent = data.class_name || 'Class';
    document.getElementById('studentId').textContent = data.id || '';
    
    if (data.avatar) {
      document.getElementById('studentAvatar').src = data.avatar;
    }

    // Render tabs data
    this.renderAcademic(data.academic);
    this.renderFinance(data.finance);
    this.renderEngagement(data.engagement);
    this.renderDocuments(data.documents);
  }

  renderAcademic(data) {
    const perfDiv = document.getElementById('academicPerformance');
    if (!perfDiv) return;

    const subjects = data && Array.isArray(data.subjects) ? data.subjects : [];
    if (!subjects.length) {
      this.setPanelState('academicPerformance', 'empty', 'No academic records are available yet.');
      return;
    }

    perfDiv.innerHTML = subjects.map(subject => `
      <div class="subject-card">
        <div class="subject-name">${subject.name}</div>
        <div class="subject-grade">${subject.grade || 'N/A'}</div>
      </div>
    `).join('');
  }

  renderFinance(data) {
    const feeDiv = document.getElementById('feeStatus');
    if (!feeDiv) return;
    if (!data || typeof data !== 'object') {
      this.setPanelState('feeStatus', 'empty', 'No finance records are available yet.');
      return;
    }

    feeDiv.innerHTML = `
      <div class="info-card">
        <span class="info-label">Total Fees</span>
        <span class="info-value">${data.total_fees || 'N/A'}</span>
      </div>
      <div class="info-card">
        <span class="info-label">Paid</span>
        <span class="info-value" style="color: var(--ds-success);">${data.paid || 'N/A'}</span>
      </div>
      <div class="info-card">
        <span class="info-label">Outstanding</span>
        <span class="info-value" style="color: var(--ds-danger);">${data.outstanding || 'N/A'}</span>
      </div>
    `;

    const paymentHistory = document.getElementById('paymentHistory');
    const outstandingBalance = document.getElementById('outstandingBalance');
    if (paymentHistory) {
      const payments = Array.isArray(data.payments) ? data.payments : [];
      paymentHistory.innerHTML = payments.length
        ? payments.map(payment => `<div class="small mb-1">${payment}</div>`).join('')
        : '<p class="text-muted small mb-0">No payments recorded yet.</p>';
    }
    if (outstandingBalance) {
      outstandingBalance.innerHTML = `<p class="small mb-0">${data.outstanding || 'No outstanding balance.'}</p>`;
    }
  }

  renderEngagement(data) {
    const box = document.getElementById('participationStats');
    const activities = document.getElementById('activitiesClubs');
    const actions = document.getElementById('recentActions');
    if (!box || !activities || !actions) return;
    if (!data || typeof data !== 'object') {
      this.setPanelState('participationStats', 'empty', 'No engagement data yet.');
      activities.innerHTML = '<p class="text-muted small mb-0">No club or activity records yet.</p>';
      actions.innerHTML = '<p class="text-muted small mb-0">No recent actions yet.</p>';
      return;
    }
    box.innerHTML = `<p class="small mb-0">${data.summary || 'Engagement summary pending.'}</p>`;
    activities.innerHTML = Array.isArray(data.activities) && data.activities.length
      ? data.activities.map(item => `<div class="small mb-1">${item}</div>`).join('')
      : '<p class="text-muted small mb-0">No club or activity records yet.</p>';
    actions.innerHTML = Array.isArray(data.recent_actions) && data.recent_actions.length
      ? data.recent_actions.map(item => `<div class="small mb-1">${item}</div>`).join('')
      : '<p class="text-muted small mb-0">No recent actions yet.</p>';
  }

  renderDocuments(data) {
    const docs = document.getElementById('documentsList');
    const reportCards = document.getElementById('reportCards');
    const certificates = document.getElementById('certificates');
    if (!docs || !reportCards || !certificates) return;
    if (!data || typeof data !== 'object') {
      this.setPanelState('documentsList', 'empty', 'No documents available yet.');
      reportCards.innerHTML = '<p class="text-muted small mb-0">No report cards published yet.</p>';
      certificates.innerHTML = '<p class="text-muted small mb-0">No certificates available yet.</p>';
      return;
    }
    docs.innerHTML = Array.isArray(data.documents) && data.documents.length
      ? data.documents.map(item => `<div class="small mb-1">${item}</div>`).join('')
      : '<p class="text-muted small mb-0">No documents available yet.</p>';
    reportCards.innerHTML = Array.isArray(data.report_cards) && data.report_cards.length
      ? data.report_cards.map(item => `<div class="small mb-1">${item}</div>`).join('')
      : '<p class="text-muted small mb-0">No report cards published yet.</p>';
    certificates.innerHTML = Array.isArray(data.certificates) && data.certificates.length
      ? data.certificates.map(item => `<div class="small mb-1">${item}</div>`).join('')
      : '<p class="text-muted small mb-0">No certificates available yet.</p>';
  }

  setPanelState(id, state, message) {
    const el = document.getElementById(id);
    if (!el) return;
    var tone = state === 'error' ? 'danger' : (state === 'loading' ? 'secondary' : 'muted');
    el.innerHTML = `<p class="text-${tone} small mb-0">${message}</p>`;
  }
}

// Initialize when ready
document.addEventListener('DOMContentLoaded', () => {
  window.student360 = new Student360();
});
