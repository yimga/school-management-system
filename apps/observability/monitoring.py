"""
Phase 8 Task 11: Monitoring & Observability
System health checks, performance monitoring, health endpoints
"""

from django.db import models, connection
from django.core.cache import cache
from django.utils import timezone
from django.http import JsonResponse
from django.views import View
from typing import Dict, List, Tuple, Optional
import json
import time
import psutil
import logging


logger = logging.getLogger(__name__)


class SystemHealthMetric(models.Model):
    """Track system health metrics"""
    
    METRIC_TYPES = [
        ('CPU', 'CPU Usage'),
        ('MEMORY', 'Memory Usage'),
        ('DISK', 'Disk Usage'),
        ('DATABASE', 'Database Health'),
        ('API_RESPONSE', 'API Response Time'),
        ('CACHE', 'Cache Hit Rate'),
        ('ERROR_RATE', 'Error Rate'),
    ]
    
    metric_type = models.CharField(max_length=20, choices=METRIC_TYPES, db_index=True)
    value = models.FloatField()
    threshold = models.FloatField(default=100.0)
    status = models.CharField(max_length=20, default='healthy')  # healthy, warning, critical
    recorded_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['metric_type', 'recorded_at']),
            models.Index(fields=['status', 'recorded_at']),
        ]
    
    def __str__(self):
        return f"{self.metric_type}: {self.value} ({self.status})"


class HealthCheckAlert(models.Model):
    """Alert when health metrics exceed thresholds"""
    
    SEVERITY_CHOICES = [
        ('INFO', 'Information'),
        ('WARNING', 'Warning'),
        ('CRITICAL', 'Critical'),
    ]
    
    metric = models.ForeignKey(SystemHealthMetric, on_delete=models.CASCADE)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.severity}: {self.message[:50]}"


class PerformanceTrace(models.Model):
    """Trace performance of operations"""
    
    operation_name = models.CharField(max_length=255, db_index=True)
    duration_ms = models.FloatField()
    memory_used_mb = models.FloatField(default=0)
    query_count = models.IntegerField(default=0)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    user_id = models.IntegerField(null=True, blank=True)
    traced_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['operation_name', 'traced_at']),
            models.Index(fields=['success', 'traced_at']),
        ]
    
    def __str__(self):
        return f"{self.operation_name} - {self.duration_ms}ms"


class AnomalyDetection(models.Model):
    """Detect anomalies in system behavior"""
    
    metric_type = models.CharField(max_length=50, db_index=True)
    anomaly_type = models.CharField(max_length=50)  # spike, drop, sustained_high, etc.
    baseline_value = models.FloatField()
    current_value = models.FloatField()
    deviation_percent = models.FloatField()
    confidence = models.FloatField(default=0.8)  # 0.0 to 1.0
    detected_at = models.DateTimeField(auto_now_add=True)
    investigation_notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.metric_type}: {self.anomaly_type} ({self.confidence*100:.0f}% confidence)"


class SystemHealthMonitor:
    """Monitor system health metrics"""
    
    ALERT_THRESHOLDS = {
        'cpu_usage': 80.0,
        'memory_usage': 85.0,
        'disk_usage': 90.0,
        'api_response_time': 2000,  # ms
        'error_rate': 5.0,  # percent
        'db_connection_pool': 20,
    }
    
    @staticmethod
    def get_cpu_usage() -> float:
        """Get CPU usage percentage"""
        try:
            return psutil.cpu_percent(interval=0.1)
        except Exception as e:
            logger.error(f"Error getting CPU usage: {e}")
            return 0.0
    
    @staticmethod
    def get_memory_usage() -> Tuple[float, float]:
        """Get memory usage (percent, used_mb)"""
        try:
            mem = psutil.virtual_memory()
            return mem.percent, mem.used / (1024 * 1024)
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return 0.0, 0.0
    
    @staticmethod
    def get_disk_usage() -> Tuple[float, float]:
        """Get disk usage (percent, free_gb)"""
        try:
            disk = psutil.disk_usage('/')
            return disk.percent, disk.free / (1024 * 1024 * 1024)
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return 0.0, 0.0
    
    @staticmethod
    def check_database_health() -> Dict:
        """Check database connectivity and performance"""
        try:
            start = time.time()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            duration = (time.time() - start) * 1000
            
            return {
                'status': 'healthy',
                'response_time_ms': duration,
                'connections': len(connection.queries) if hasattr(connection, 'queries') else 0,
            }
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return {
                'status': 'unhealthy',
                'response_time_ms': 0,
                'error': str(e),
            }
    
    @staticmethod
    def check_cache_health() -> Dict:
        """Check cache system health"""
        try:
            test_key = 'health_check_test'
            test_value = 'test_value'
            
            cache.set(test_key, test_value, 10)
            retrieved = cache.get(test_key)
            cache.delete(test_key)
            
            return {
                'status': 'healthy' if retrieved == test_value else 'unhealthy',
                'type': type(cache).__name__,
            }
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e),
            }
    
    @staticmethod
    def get_comprehensive_health() -> Dict:
        """Get comprehensive system health"""
        cpu = SystemHealthMonitor.get_cpu_usage()
        mem_percent, mem_used = SystemHealthMonitor.get_memory_usage()
        disk_percent, disk_free = SystemHealthMonitor.get_disk_usage()
        db_health = SystemHealthMonitor.check_database_health()
        cache_health = SystemHealthMonitor.check_cache_health()
        
        # Determine overall status
        statuses = []
        if cpu > SystemHealthMonitor.ALERT_THRESHOLDS['cpu_usage']:
            statuses.append('warning')
        if mem_percent > SystemHealthMonitor.ALERT_THRESHOLDS['memory_usage']:
            statuses.append('warning')
        if disk_percent > SystemHealthMonitor.ALERT_THRESHOLDS['disk_usage']:
            statuses.append('critical')
        if db_health['status'] != 'healthy':
            statuses.append('critical')
        
        overall_status = 'critical' if 'critical' in statuses else ('warning' if 'warning' in statuses else 'healthy')
        
        return {
            'overall_status': overall_status,
            'cpu': {
                'usage_percent': cpu,
                'threshold': SystemHealthMonitor.ALERT_THRESHOLDS['cpu_usage'],
                'status': 'warning' if cpu > SystemHealthMonitor.ALERT_THRESHOLDS['cpu_usage'] else 'healthy',
            },
            'memory': {
                'usage_percent': mem_percent,
                'used_mb': mem_used,
                'threshold': SystemHealthMonitor.ALERT_THRESHOLDS['memory_usage'],
                'status': 'warning' if mem_percent > SystemHealthMonitor.ALERT_THRESHOLDS['memory_usage'] else 'healthy',
            },
            'disk': {
                'usage_percent': disk_percent,
                'free_gb': disk_free,
                'threshold': SystemHealthMonitor.ALERT_THRESHOLDS['disk_usage'],
                'status': 'critical' if disk_percent > SystemHealthMonitor.ALERT_THRESHOLDS['disk_usage'] else 'healthy',
            },
            'database': db_health,
            'cache': cache_health,
            'timestamp': timezone.now().isoformat(),
        }
    
    @staticmethod
    def record_metric(metric_type: str, value: float, threshold: float = 100.0):
        """Record a health metric"""
        status = 'healthy'
        if value > threshold:
            status = 'critical' if value > threshold * 1.2 else 'warning'
        
        metric = SystemHealthMetric.objects.create(
            metric_type=metric_type,
            value=value,
            threshold=threshold,
            status=status
        )
        
        # Create alert if needed
        if status != 'healthy':
            HealthCheckAlert.objects.create(
                metric=metric,
                severity='CRITICAL' if status == 'critical' else 'WARNING',
                message=f"{metric_type} exceeded threshold: {value:.2f} > {threshold}"
            )
        
        return metric


class PerformanceProfiler:
    """Profile performance of operations"""
    
    def __init__(self, operation_name: str, user_id: Optional[int] = None):
        self.operation_name = operation_name
        self.user_id = user_id
        self.start_time = None
        self.start_memory = None
    
    def __enter__(self):
        self.start_time = time.time()
        try:
            self.start_memory = psutil.Process().memory_info().rss / (1024 * 1024)
        except:
            self.start_memory = 0
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000
        
        try:
            end_memory = psutil.Process().memory_info().rss / (1024 * 1024)
            memory_used = end_memory - self.start_memory
        except:
            memory_used = 0
        
        error_message = ''
        success = exc_type is None
        
        if not success:
            error_message = str(exc_val)
        
        PerformanceTrace.objects.create(
            operation_name=self.operation_name,
            duration_ms=duration_ms,
            memory_used_mb=memory_used,
            success=success,
            error_message=error_message,
            user_id=self.user_id
        )


class AnomalyDetector:
    """Detect anomalies in metrics"""
    
    @staticmethod
    def calculate_baseline(metric_type: str, days: int = 7) -> float:
        """Calculate baseline value for metric"""
        from datetime import timedelta
        
        cutoff = timezone.now() - timedelta(days=days)
        metrics = SystemHealthMetric.objects.filter(
            metric_type=metric_type,
            recorded_at__gte=cutoff,
            status='healthy'
        )
        
        if not metrics.exists():
            return 0.0
        
        values = list(metrics.values_list('value', flat=True))
        return sum(values) / len(values) if values else 0.0
    
    @staticmethod
    def detect_spike(metric_type: str, current_value: float) -> bool:
        """Detect spike in metric"""
        baseline = AnomalyDetector.calculate_baseline(metric_type)
        
        if baseline == 0:
            return False
        
        deviation = ((current_value - baseline) / baseline) * 100
        
        if deviation > 50:  # 50% increase
            AnomalyDetection.objects.create(
                metric_type=metric_type,
                anomaly_type='spike',
                baseline_value=baseline,
                current_value=current_value,
                deviation_percent=deviation,
                confidence=min(1.0, abs(deviation) / 100.0)
            )
            return True
        
        return False


class HealthCheckEndpoint(View):
    """Health check endpoint for monitoring"""
    
    def get(self, request):
        """GET /health - Return system health status"""
        health = SystemHealthMonitor.get_comprehensive_health()
        status_code = 200 if health['overall_status'] == 'healthy' else 503
        
        return JsonResponse(health, status=status_code)


class DetailedHealthCheckEndpoint(View):
    """Detailed health check with historical data"""
    
    def get(self, request):
        """GET /health/detailed - Return detailed health report"""
        # Get current health
        current = SystemHealthMonitor.get_comprehensive_health()
        
        # Get recent metrics
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=24)
        
        recent_metrics = SystemHealthMetric.objects.filter(
            recorded_at__gte=cutoff
        ).values('metric_type').annotate(
            avg_value=models.Avg('value'),
            max_value=models.Max('value'),
            min_value=models.Min('value'),
            warning_count=models.Count('id', filter=models.Q(status='warning')),
            critical_count=models.Count('id', filter=models.Q(status='critical')),
        )
        
        # Get active alerts
        active_alerts = HealthCheckAlert.objects.filter(
            is_resolved=False
        ).count()
        
        return JsonResponse({
            'current_health': current,
            'recent_metrics': list(recent_metrics),
            'active_alerts': active_alerts,
            'timestamp': timezone.now().isoformat(),
        })


class MetricsHistoryEndpoint(View):
    """Historical metrics endpoint"""
    
    def get(self, request):
        """GET /metrics/history - Return historical metrics"""
        hours = int(request.GET.get('hours', 24))
        metric_type = request.GET.get('type')
        
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=hours)
        
        query = SystemHealthMetric.objects.filter(recorded_at__gte=cutoff)
        
        if metric_type:
            query = query.filter(metric_type=metric_type)
        
        data = list(query.values(
            'metric_type',
            'value',
            'status',
            'recorded_at'
        ).order_by('recorded_at'))
        
        return JsonResponse({
            'metrics': data,
            'period_hours': hours,
            'total_records': len(data),
        })
