"""
Phase 8 Task 11: Monitoring & Observability Tests
System health checks, performance monitoring, anomaly detection
"""

from django.test import TestCase, Client, override_settings
from django.utils import timezone
from datetime import timedelta


class SystemHealthMetricTestCase(TestCase):
    """Test health metric recording"""
    
    def test_create_health_metric(self):
        """Test creating health metric"""
        from apps.observability.monitoring import SystemHealthMetric
        
        metric = SystemHealthMetric.objects.create(
            metric_type='CPU',
            value=45.5,
            threshold=80.0,
            status='healthy'
        )
        
        self.assertEqual(metric.value, 45.5)
        self.assertEqual(metric.status, 'healthy')
    
    def test_metric_query_by_type(self):
        """Test querying metrics by type"""
        from apps.observability.monitoring import SystemHealthMetric
        
        SystemHealthMetric.objects.create(metric_type='CPU', value=50.0)
        SystemHealthMetric.objects.create(metric_type='MEMORY', value=60.0)
        
        cpu_metrics = SystemHealthMetric.objects.filter(metric_type='CPU')
        
        self.assertEqual(cpu_metrics.count(), 1)


class HealthCheckAlertTestCase(TestCase):
    """Test health check alerts"""
    
    def setUp(self):
        from apps.observability.monitoring import SystemHealthMetric, HealthCheckAlert
        
        self.metric = SystemHealthMetric.objects.create(
            metric_type='CPU',
            value=85.0,
            status='warning'
        )
    
    def test_create_alert(self):
        """Test creating alert"""
        from apps.observability.monitoring import HealthCheckAlert
        
        alert = HealthCheckAlert.objects.create(
            metric=self.metric,
            severity='WARNING',
            message='CPU usage above threshold'
        )
        
        self.assertFalse(alert.is_resolved)
    
    def test_resolve_alert(self):
        """Test resolving alert"""
        from apps.observability.monitoring import HealthCheckAlert
        
        alert = HealthCheckAlert.objects.create(
            metric=self.metric,
            severity='CRITICAL',
            message='Memory critical'
        )
        
        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.save()
        
        self.assertTrue(alert.is_resolved)
        self.assertIsNotNone(alert.resolved_at)


class PerformanceTraceTestCase(TestCase):
    """Test performance tracing"""
    
    def test_create_trace(self):
        """Test creating performance trace"""
        from apps.observability.monitoring import PerformanceTrace
        
        trace = PerformanceTrace.objects.create(
            operation_name='user_login',
            duration_ms=45.5,
            memory_used_mb=2.3,
            query_count=3,
            success=True
        )
        
        self.assertEqual(trace.operation_name, 'user_login')
        self.assertTrue(trace.success)
    
    def test_trace_failed_operation(self):
        """Test tracing failed operation"""
        from apps.observability.monitoring import PerformanceTrace
        
        trace = PerformanceTrace.objects.create(
            operation_name='data_export',
            duration_ms=120.0,
            success=False,
            error_message='Out of memory'
        )
        
        self.assertFalse(trace.success)
        self.assertIn('memory', trace.error_message.lower())


class AnomalyDetectionTestCase(TestCase):
    """Test anomaly detection"""
    
    def test_create_anomaly(self):
        """Test recording anomaly"""
        from apps.observability.monitoring import AnomalyDetection
        
        anomaly = AnomalyDetection.objects.create(
            metric_type='CPU',
            anomaly_type='spike',
            baseline_value=40.0,
            current_value=85.0,
            deviation_percent=112.5
        )
        
        self.assertEqual(anomaly.anomaly_type, 'spike')
        self.assertGreater(anomaly.deviation_percent, 100)


class SystemHealthMonitorTestCase(TestCase):
    """Test system health monitoring"""
    
    def test_get_cpu_usage(self):
        """Test CPU usage retrieval"""
        from apps.observability.monitoring import SystemHealthMonitor
        
        cpu = SystemHealthMonitor.get_cpu_usage()
        
        self.assertGreaterEqual(cpu, 0)
        self.assertLessEqual(cpu, 100)
    
    def test_get_memory_usage(self):
        """Test memory usage retrieval"""
        from apps.observability.monitoring import SystemHealthMonitor
        
        percent, used = SystemHealthMonitor.get_memory_usage()
        
        self.assertGreaterEqual(percent, 0)
        self.assertGreater(used, 0)
    
    def test_get_disk_usage(self):
        """Test disk usage retrieval"""
        from apps.observability.monitoring import SystemHealthMonitor
        
        percent, free = SystemHealthMonitor.get_disk_usage()
        
        self.assertGreaterEqual(percent, 0)
        self.assertGreater(free, 0)
    
    def test_check_database_health(self):
        """Test database health check"""
        from apps.observability.monitoring import SystemHealthMonitor
        
        health = SystemHealthMonitor.check_database_health()
        
        self.assertIn('status', health)
        self.assertIn('response_time_ms', health)
    
    def test_check_cache_health(self):
        """Test cache health check"""
        from apps.observability.monitoring import SystemHealthMonitor
        
        health = SystemHealthMonitor.check_cache_health()
        
        self.assertIn('status', health)
        self.assertEqual(health['status'], 'healthy')
    
    def test_get_comprehensive_health(self):
        """Test comprehensive health check"""
        from apps.observability.monitoring import SystemHealthMonitor
        
        health = SystemHealthMonitor.get_comprehensive_health()
        
        self.assertIn('overall_status', health)
        self.assertIn('cpu', health)
        self.assertIn('memory', health)
        self.assertIn('disk', health)
        self.assertIn('database', health)
        self.assertIn('cache', health)
    
    def test_record_metric(self):
        """Test recording metric"""
        from apps.observability.monitoring import SystemHealthMonitor
        
        metric = SystemHealthMonitor.record_metric('CPU', 75.0, threshold=80.0)
        
        self.assertEqual(metric.status, 'healthy')

    def test_record_metric_creates_and_resolves_platform_incident(self):
        from apps.observability.models import PlatformIncident
        from apps.observability.monitoring import SystemHealthMonitor

        SystemHealthMonitor.record_metric('CPU', 99.0, threshold=80.0)

        incident = PlatformIncident.objects.get(source_system="observability.healthcheck")
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)
        self.assertEqual(incident.severity, PlatformIncident.Severity.CRITICAL)

        SystemHealthMonitor.record_metric('CPU', 55.0, threshold=80.0)

        incident.refresh_from_db()
        self.assertEqual(incident.status, PlatformIncident.Status.RESOLVED)


class PerformanceProfilerTestCase(TestCase):
    """Test performance profiler"""
    
    def test_profile_operation(self):
        """Test profiling operation"""
        from apps.observability.monitoring import PerformanceProfiler
        import time
        
        with PerformanceProfiler('test_operation', user_id=1) as profiler:
            time.sleep(0.01)  # Sleep 10ms
        
        # Operation should be recorded
    
    def test_profile_failed_operation(self):
        """Test profiling failed operation"""
        from apps.observability.monitoring import PerformanceProfiler
        
        try:
            with PerformanceProfiler('failing_operation') as profiler:
                raise ValueError('Test error')
        except ValueError:
            pass


class AnomalyDetectorTestCase(TestCase):
    """Test anomaly detection"""
    
    def setUp(self):
        from apps.observability.monitoring import SystemHealthMetric
        
        # Create baseline metrics
        for i in range(10):
            SystemHealthMetric.objects.create(
                metric_type='CPU',
                value=50.0 + (i % 5),
                status='healthy',
                recorded_at=timezone.now() - timedelta(days=i)
            )
    
    def test_calculate_baseline(self):
        """Test baseline calculation"""
        from apps.observability.monitoring import AnomalyDetector
        
        baseline = AnomalyDetector.calculate_baseline('CPU', days=7)
        
        self.assertGreater(baseline, 0)
    
    def test_detect_spike(self):
        """Test spike detection"""
        from apps.observability.monitoring import AnomalyDetector
        
        # Create spike
        spike_detected = AnomalyDetector.detect_spike('CPU', 95.0)
        
        # Baseline is around 50, spike is 95, so should detect
        self.assertTrue(spike_detected)


class HealthCheckEndpointTestCase(TestCase):
    """Test health check endpoints"""
    
    def setUp(self):
        self.client = Client()
    
    def test_health_endpoint(self):
        """Test /health endpoint"""
        response = self.client.get('/health/')
        
        self.assertIn(response.status_code, [200, 503])

    @override_settings(
        SECURE_SSL_REDIRECT=True,
        SECURE_REDIRECT_EXEMPT=[r"^$", r"^health/$", r"^healthz/$", r"^ready/$", r"^status/$", r"^api/health/$"],
    )
    def test_health_endpoint_exempt_from_ssl_redirect(self):
        """Health endpoint should stay probe-safe even with SSL redirect enabled."""
        response = self.client.get('/health/')
        self.assertEqual(response.status_code, 200)

    @override_settings(
        SECURE_SSL_REDIRECT=True,
        SECURE_REDIRECT_EXEMPT=[r"^$", r"^health/$", r"^healthz/$", r"^ready/$", r"^status/$", r"^api/health/$"],
    )
    def test_root_endpoint_exempt_from_ssl_redirect(self):
        """Root should avoid HTTP->HTTPS redirect so platform startup probes can pass."""
        response = self.client.get('/')
        self.assertNotEqual(response.status_code, 301)
    
    def test_health_response_format(self):
        """Test health response structure"""
        from apps.observability.monitoring import HealthCheckEndpoint
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/health/')
        
        view = HealthCheckEndpoint.as_view()
        response = view(request)
        
        self.assertEqual(response.status_code, 200)


class DetailedHealthCheckEndpointTestCase(TestCase):
    """Test detailed health endpoint"""
    
    def test_detailed_health_response(self):
        """Test detailed health response"""
        from apps.observability.monitoring import DetailedHealthCheckEndpoint
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/health/detailed/')
        
        view = DetailedHealthCheckEndpoint.as_view()
        response = view(request)
        
        self.assertEqual(response.status_code, 200)


class MetricsHistoryEndpointTestCase(TestCase):
    """Test metrics history endpoint"""
    
    def setUp(self):
        from apps.observability.monitoring import SystemHealthMetric
        
        for i in range(10):
            SystemHealthMetric.objects.create(
                metric_type='CPU' if i % 2 == 0 else 'MEMORY',
                value=50.0 + i,
                recorded_at=timezone.now() - timedelta(hours=i)
            )
    
    def test_metrics_history_response(self):
        """Test metrics history endpoint"""
        from apps.observability.monitoring import MetricsHistoryEndpoint
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/metrics/history/', {'hours': 24})
        
        view = MetricsHistoryEndpoint.as_view()
        response = view(request)
        
        self.assertEqual(response.status_code, 200)
    
    def test_metrics_history_by_type(self):
        """Test metrics history filtered by type"""
        from apps.observability.monitoring import MetricsHistoryEndpoint
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/metrics/history/', {'hours': 24, 'type': 'CPU'})
        
        view = MetricsHistoryEndpoint.as_view()
        response = view(request)
        
        self.assertEqual(response.status_code, 200)
