"""
Phase 8 Task 11: Monitoring & Observability
System health checks, performance monitoring, health endpoints
"""

import uuid
from django.conf import settings
from django.db import models, connection
from django.core.cache import cache
from django.utils import timezone
from django.http import JsonResponse
from django.views import View
from typing import Dict, List, Tuple, Optional
import json
import os
import shutil
import time
import logging
import platform

try:
    import psutil
except Exception:  # pragma: no cover - optional dependency
    psutil = None


logger = logging.getLogger(__name__)

MB = 1024 * 1024
GB = 1024 * 1024 * 1024


def _read_process_rss_mb() -> float:
    """Return current process RSS in MB without requiring psutil."""
    if psutil is not None:
        try:
            return psutil.Process().memory_info().rss / MB
        except Exception:
            pass

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        # Linux reports KB, macOS reports bytes.
        if platform.system() == "Darwin":
            rss_mb = float(usage.ru_maxrss) / MB
        else:
            rss_mb = float(usage.ru_maxrss) / 1024
        if rss_mb > 0:
            return rss_mb
    except Exception:
        pass

    return 0.0


def _read_memory_usage() -> Tuple[float, float]:
    """
    Return memory usage tuple: (percent, used_mb).
    Falls back to OS APIs when psutil is unavailable.
    """
    if psutil is not None:
        mem = psutil.virtual_memory()
        return float(mem.percent), float(mem.used) / MB

    # Windows fallback.
    if platform.system() == "Windows":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            memory_status = MEMORYSTATUSEX()
            memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
                total = float(memory_status.ullTotalPhys)
                available = float(memory_status.ullAvailPhys)
                used = max(total - available, 0.0)
                percent = (used / total * 100.0) if total > 0 else 0.0
                return percent, max(used / MB, 0.001)
        except Exception:
            pass

    # POSIX fallback.
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        total_pages = os.sysconf("SC_PHYS_PAGES")
        avail_pages = os.sysconf("SC_AVPHYS_PAGES")
        total = float(page_size * total_pages)
        available = float(page_size * avail_pages)
        used = max(total - available, 0.0)
        percent = (used / total * 100.0) if total > 0 else 0.0
        return percent, max(used / MB, 0.001)
    except Exception:
        pass

    # Last fallback: expose at least process memory.
    return 0.0, max(_read_process_rss_mb(), 0.001)


def _read_disk_usage(path: str = "/") -> Tuple[float, float]:
    """
    Return disk usage tuple: (percent_used, free_gb).
    Uses stdlib fallback when psutil is unavailable.
    """
    if psutil is not None:
        disk = psutil.disk_usage(path)
        return float(disk.percent), max(float(disk.free) / GB, 0.001)

    total, used, free = shutil.disk_usage(path)
    percent = (float(used) / float(total) * 100.0) if total > 0 else 0.0
    return percent, max(float(free) / GB, 0.001)


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


class PlatformIncident(models.Model):
    """Shared-schema incident record for platform-level operations."""

    class IncidentType(models.TextChoices):
        AVAILABILITY = "availability", "Availability"
        PERFORMANCE = "performance", "Performance"
        SECURITY = "security", "Security"
        DATA = "data", "Data integrity"
        INTEGRATION = "integration", "Integration"
        BILLING = "billing", "Billing"
        DEPLOYMENT = "deployment", "Deployment"
        SUPPORT = "support", "Support escalation"
        OTHER = "other", "Other"

    class Severity(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        MITIGATED = "mitigated", "Mitigated"
        RESOLVED = "resolved", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    incident_type = models.CharField(
        max_length=32,
        choices=IncidentType.choices,
        default=IncidentType.OTHER,
        db_index=True,
    )
    severity = models.CharField(
        max_length=16,
        choices=Severity.choices,
        default=Severity.MEDIUM,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    summary = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    source_system = models.CharField(max_length=128, blank=True)
    affected_school = models.ForeignKey(
        "schools.School",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_incidents",
    )
    affected_schema_name = models.CharField(max_length=63, blank=True, db_index=True)
    detected_at = models.DateTimeField(default=timezone.now, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_incidents_created",
    )
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_incidents_acknowledged",
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_incidents_resolved",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-detected_at", "-created_at"]
        indexes = [
            models.Index(fields=["status", "severity", "detected_at"]),
            models.Index(fields=["incident_type", "detected_at"]),
        ]

    def __str__(self):
        return f"{self.severity.upper()} {self.title}"


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
            if psutil is None:
                return 0.0
            return float(psutil.cpu_percent(interval=0.1))
        except Exception as e:
            logger.error(f"Error getting CPU usage: {e}")
            return 0.0
    
    @staticmethod
    def get_memory_usage() -> Tuple[float, float]:
        """Get memory usage (percent, used_mb)"""
        try:
            return _read_memory_usage()
        except Exception as e:
            logger.error(f"Error getting memory usage: {e}")
            return 0.0, 0.001
    
    @staticmethod
    def get_disk_usage() -> Tuple[float, float]:
        """Get disk usage (percent, free_gb)"""
        try:
            return _read_disk_usage("/")
        except Exception as e:
            logger.error(f"Error getting disk usage: {e}")
            return 0.0, 0.001
    
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
        self.start_memory = _read_process_rss_mb()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start_time) * 1000

        end_memory = _read_process_rss_mb()
        memory_used = max(end_memory - (self.start_memory or 0.0), 0.0)
        
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
        # Liveness/readiness should fail only when core dependencies fail.
        # Resource pressure (CPU/memory/disk warnings) remains visible in payload
        # but should not return 503 by itself.
        database_unhealthy = health.get("database", {}).get("status") != "healthy"
        cache_unhealthy = health.get("cache", {}).get("status") != "healthy"
        status_code = 503 if (database_unhealthy or cache_unhealthy) else 200
        
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
