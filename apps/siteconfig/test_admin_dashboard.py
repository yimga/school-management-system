"""
Phase 8 Task 9: Admin Dashboard Tests
Dashboard metrics, widgets, customization tests
"""

from django.test import TestCase
from django.utils import timezone


class AdminDashboardServiceTestCase(TestCase):
    """Test admin dashboard service"""
    
    def test_get_student_metrics(self):
        """Test student metrics"""
        from apps.siteconfig.admin_dashboard import AdminDashboardService
        
        metrics = AdminDashboardService.get_student_metrics()
        
        self.assertIn('total', metrics)
        self.assertIn('active', metrics)
        self.assertIn('inactive', metrics)
        self.assertIn('percentage', metrics)
    
    def test_get_teacher_metrics(self):
        """Test teacher metrics"""
        from apps.siteconfig.admin_dashboard import AdminDashboardService
        
        metrics = AdminDashboardService.get_teacher_metrics()
        
        self.assertIn('total', metrics)
        self.assertIn('active', metrics)
        self.assertIn('qualifications', metrics)
    
    def test_get_academic_metrics(self):
        """Test academic metrics"""
        from apps.siteconfig.admin_dashboard import AdminDashboardService
        
        metrics = AdminDashboardService.get_academic_metrics()
        
        self.assertIn('classrooms', metrics)
        self.assertIn('evaluations_this_month', metrics)
        self.assertIn('average_score', metrics)
    
    def test_get_finance_metrics(self):
        """Test finance metrics"""
        from apps.siteconfig.admin_dashboard import AdminDashboardService
        
        metrics = AdminDashboardService.get_finance_metrics()
        
        self.assertIn('total_revenue', metrics)
        self.assertIn('monthly_revenue', metrics)
        self.assertIn('pending_invoices', metrics)
    
    def test_get_attendance_metrics(self):
        """Test attendance metrics"""
        from apps.siteconfig.admin_dashboard import AdminDashboardService
        
        metrics = AdminDashboardService.get_attendance_metrics()
        
        self.assertIn('attendance_rate', metrics)
        self.assertGreaterEqual(metrics['attendance_rate'], 0)
    
    def test_get_system_health(self):
        """Test system health"""
        from apps.siteconfig.admin_dashboard import AdminDashboardService
        
        health = AdminDashboardService.get_system_health()
        
        self.assertEqual(health['database_status'], 'healthy')
        self.assertEqual(health['api_status'], 'online')


class AdminDashboardWidgetTestCase(TestCase):
    """Test dashboard widgets"""
    
    def test_create_widget(self):
        """Test creating widget"""
        from apps.siteconfig.admin_dashboard import AdminDashboardWidget
        
        widget = AdminDashboardWidget('Test Widget', 'count')
        widget.value = 42
        
        self.assertEqual(widget.value, 42)
        self.assertEqual(widget.get_formatted_value(), '42')
    
    def test_percentage_widget(self):
        """Test percentage formatting"""
        from apps.siteconfig.admin_dashboard import AdminDashboardWidget
        
        widget = AdminDashboardWidget('Rate', 'percentage')
        widget.value = 85.5
        
        self.assertEqual(widget.get_formatted_value(), '85.5%')
    
    def test_currency_widget(self):
        """Test currency formatting"""
        from apps.siteconfig.admin_dashboard import AdminDashboardWidget
        
        widget = AdminDashboardWidget('Revenue', 'currency')
        widget.value = 50000
        
        formatted = widget.get_formatted_value()
        self.assertIn('₦', formatted)


class QuickStatsWidgetTestCase(TestCase):
    """Test quick stats widget"""
    
    def test_add_stat(self):
        """Test adding stats"""
        from apps.siteconfig.admin_dashboard import QuickStatsWidget
        
        widget = QuickStatsWidget()
        widget.add_stat('Students', 150)
        widget.add_stat('Teachers', 25)
        
        self.assertEqual(len(widget.stats), 2)
        self.assertEqual(widget.stats['Students'], 150)


class ChartWidgetTestCase(TestCase):
    """Test chart widget"""
    
    def test_set_chart_data(self):
        """Test setting chart data"""
        from apps.siteconfig.admin_dashboard import ChartWidget
        
        widget = ChartWidget('Grade Distribution', 'bar')
        widget.set_data(['A', 'B', 'C', 'D', 'F'], [30, 40, 20, 7, 3])
        
        self.assertEqual(len(widget.labels), 5)
        self.assertEqual(len(widget.data), 5)


class AlertWidgetTestCase(TestCase):
    """Test alert widget"""
    
    def test_add_alerts(self):
        """Test adding alerts"""
        from apps.siteconfig.admin_dashboard import AlertWidget
        
        widget = AlertWidget()
        widget.add_alert('Critical issue detected', 'critical')
        widget.add_alert('Low disk space', 'warning')
        widget.add_alert('Backup completed', 'info')
        
        self.assertEqual(len(widget.alerts), 3)


class AdminDashboardViewTestCase(TestCase):
    """Test main dashboard view"""
    
    def test_create_dashboard(self):
        """Test creating dashboard"""
        from apps.siteconfig.admin_dashboard import AdminDashboardView, AdminDashboardWidget
        
        dashboard = AdminDashboardView()
        
        widget1 = AdminDashboardWidget('Students', 'count')
        widget1.value = 150
        
        widget2 = AdminDashboardWidget('Teachers', 'count')
        widget2.value = 25
        
        dashboard.add_widget(widget1, 'overview')
        dashboard.add_widget(widget2, 'overview')
        
        self.assertEqual(len(dashboard.sections['overview']), 2)
    
    def test_get_metrics_json(self):
        """Test getting metrics as JSON"""
        from apps.siteconfig.admin_dashboard import AdminDashboardView
        import json
        
        dashboard = AdminDashboardView()
        metrics_json = dashboard.get_metrics_json()
        
        metrics = json.loads(metrics_json)
        self.assertIn('students', metrics)
        self.assertIn('teachers', metrics)


class AdminCustomizationServiceTestCase(TestCase):
    """Test admin customization"""
    
    def test_get_preferences(self):
        """Test getting preferences"""
        from apps.siteconfig.admin_dashboard import AdminCustomizationService
        
        prefs = AdminCustomizationService.get_admin_preferences(1)
        
        self.assertIn('dashboard_layout', prefs)
        self.assertIn('notifications_enabled', prefs)
    
    def test_save_preferences(self):
        """Test saving preferences"""
        from apps.siteconfig.admin_dashboard import AdminCustomizationService
        
        prefs = {'dashboard_layout': 'compact', 'auto_refresh': False}
        result = AdminCustomizationService.save_admin_preferences(1, prefs)
        
        self.assertEqual(result['status'], 'saved')
    
    def test_get_custom_reports(self):
        """Test getting custom reports"""
        from apps.siteconfig.admin_dashboard import AdminCustomizationService
        
        reports = AdminCustomizationService.get_custom_reports(1)
        
        self.assertGreater(len(reports), 0)
        self.assertIn('name', reports[0])


class AdminNotificationServiceTestCase(TestCase):
    """Test admin notifications"""
    
    def test_get_pending_notifications(self):
        """Test getting notifications"""
        from apps.siteconfig.admin_dashboard import AdminNotificationService
        
        notifs = AdminNotificationService.get_pending_notifications(1)
        
        self.assertIsInstance(notifs, list)
    
    def test_send_notification(self):
        """Test sending notification"""
        from apps.siteconfig.admin_dashboard import AdminNotificationService
        
        result = AdminNotificationService.send_notification(
            1,
            'Test Alert',
            'This is a test',
            'warning'
        )
        
        self.assertEqual(result['status'], 'sent')
        self.assertIn('notification_id', result)
