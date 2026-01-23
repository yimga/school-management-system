/**
 * Dashboard Charts - Chart.js Integration
 * Enrollment trends, fee gauges, grade heatmaps, performance analytics
 */

class DashboardCharts {
  constructor() {
    this.charts = {};
    this.init();
  }

  init() {
    this.loadChartData();
    this.initCharts();
  }

  async loadChartData() {
    try {
      // Try to load data from API
      const response = await fetch('/api/dashboard/charts/');
      if (response.ok) {
        this.data = await response.json();
      } else {
        this.data = this.getDefaultData();
      }
    } catch (error) {
      console.warn('Could not load chart data from API, using defaults:', error);
      this.data = this.getDefaultData();
    }
  }

  getDefaultData() {
    return {
      enrollment: {
        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
        datasets: [{
          label: 'New Enrollments',
          data: [12, 19, 8, 15, 22, 18],
          borderColor: '#ff6a88',
          backgroundColor: 'rgba(255, 106, 136, 0.1)',
          tension: 0.4,
          fill: true,
          pointRadius: 4,
          pointHoverRadius: 6
        }]
      },
      feeCollection: {
        labels: ['Paid', 'Pending', 'Overdue'],
        datasets: [{
          data: [75, 15, 10],
          backgroundColor: ['#2dd4bf', '#9b6bff', '#ff6a88']
        }]
      },
      performance: {
        labels: ['Mathematics', 'English', 'Science', 'Social Studies', 'Arts'],
        datasets: [{
          label: 'Average Grade',
          data: [78, 82, 75, 88, 90],
          borderColor: '#9b6bff',
          backgroundColor: 'rgba(155, 107, 255, 0.1)',
          fill: true
        }]
      },
      attendance: {
        labels: ['Present', 'Absent', 'Late'],
        datasets: [{
          data: [85, 10, 5],
          backgroundColor: ['#2dd4bf', '#ff6a88', '#9b6bff']
        }]
      }
    };
  }

  initCharts() {
    this.createEnrollmentChart();
    this.createFeeCollectionChart();
    this.createPerformanceChart();
    this.createAttendanceChart();
  }

  createEnrollmentChart() {
    const canvas = document.getElementById('enrollmentChart');
    if (!canvas) return;

    this.charts.enrollment = new Chart(canvas, {
      type: 'line',
      data: this.data.enrollment,
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            display: true,
            labels: {
              color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary'),
              font: { size: 12 }
            }
          },
          title: {
            display: true,
            text: 'Enrollment Trends',
            color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary'),
            font: { size: 14, weight: 'bold' }
          }
        },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted')
            },
            grid: {
              color: 'rgba(200, 200, 200, 0.1)'
            }
          },
          x: {
            ticks: {
              color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted')
            },
            grid: {
              color: 'rgba(200, 200, 200, 0.1)'
            }
          }
        }
      }
    });
  }

  createFeeCollectionChart() {
    const canvas = document.getElementById('feeCollectionChart');
    if (!canvas) return;

    this.charts.feeCollection = new Chart(canvas, {
      type: 'doughnut',
      data: this.data.feeCollection,
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            display: true,
            labels: {
              color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary'),
              font: { size: 12 }
            }
          },
          title: {
            display: true,
            text: 'Fee Collection Status',
            color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary'),
            font: { size: 14, weight: 'bold' }
          }
        }
      }
    });
  }

  createPerformanceChart() {
    const canvas = document.getElementById('performanceChart');
    if (!canvas) return;

    this.charts.performance = new Chart(canvas, {
      type: 'radar',
      data: this.data.performance,
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: {
          legend: {
            display: true,
            labels: {
              color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary'),
              font: { size: 12 }
            }
          },
          title: {
            display: true,
            text: 'Academic Performance',
            color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary'),
            font: { size: 14, weight: 'bold' }
          }
        },
        scales: {
          r: {
            ticks: {
              color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted'),
              backdropColor: 'transparent'
            },
            grid: {
              color: 'rgba(200, 200, 200, 0.1)'
            }
          }
        }
      }
    });
  }

  createAttendanceChart() {
    const canvas = document.getElementById('attendanceChart');
    if (!canvas) return;

    this.charts.attendance = new Chart(canvas, {
      type: 'bar',
      data: this.data.attendance,
      options: {
        responsive: true,
        maintainAspectRatio: true,
        indexAxis: 'y',
        plugins: {
          legend: {
            display: false
          },
          title: {
            display: true,
            text: 'Attendance Overview',
            color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary'),
            font: { size: 14, weight: 'bold' }
          }
        },
        scales: {
          x: {
            ticks: {
              color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted')
            },
            grid: {
              color: 'rgba(200, 200, 200, 0.1)'
            }
          },
          y: {
            ticks: {
              color: getComputedStyle(document.documentElement).getPropertyValue('--color-text-muted')
            }
          }
        }
      }
    });
  }

  refreshCharts() {
    this.loadChartData().then(() => {
      Object.values(this.charts).forEach(chart => {
        if (chart) chart.destroy();
      });
      this.initCharts();
    });
  }
}

// Initialize when DOM ready
document.addEventListener('DOMContentLoaded', () => {
  // Wait for Chart.js to be available
  if (typeof Chart !== 'undefined') {
    window.dashboardCharts = new DashboardCharts();
    console.log('✅ Dashboard Charts initialized');
  } else {
    console.warn('⚠️ Chart.js library not loaded');
  }
});

// Auto-refresh charts every 5 minutes
setInterval(() => {
  if (window.dashboardCharts) {
    window.dashboardCharts.refreshCharts();
  }
}, 5 * 60 * 1000);
