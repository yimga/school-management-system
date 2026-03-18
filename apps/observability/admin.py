from django.contrib import admin

from config.admin import platform_admin_site

from .models import (
    AnomalyDetection,
    HealthCheckAlert,
    PerformanceTrace,
    PlatformIncident,
    SystemHealthMetric,
)


@admin.register(SystemHealthMetric, site=platform_admin_site)
class SystemHealthMetricAdmin(admin.ModelAdmin):
    list_display = ("metric_type", "value", "threshold", "status", "recorded_at")
    list_filter = ("metric_type", "status")
    search_fields = ("metric_type",)
    readonly_fields = ("recorded_at",)


@admin.register(HealthCheckAlert, site=platform_admin_site)
class HealthCheckAlertAdmin(admin.ModelAdmin):
    list_display = ("severity", "metric", "is_resolved", "created_at", "resolved_at")
    list_filter = ("severity", "is_resolved")
    search_fields = ("message", "metric__metric_type")
    readonly_fields = ("created_at",)


@admin.register(PerformanceTrace, site=platform_admin_site)
class PerformanceTraceAdmin(admin.ModelAdmin):
    list_display = ("operation_name", "duration_ms", "success", "user_id", "traced_at")
    list_filter = ("success",)
    search_fields = ("operation_name", "error_message")
    readonly_fields = ("traced_at",)


@admin.register(AnomalyDetection, site=platform_admin_site)
class AnomalyDetectionAdmin(admin.ModelAdmin):
    list_display = (
        "metric_type",
        "anomaly_type",
        "current_value",
        "deviation_percent",
        "detected_at",
    )
    list_filter = ("metric_type", "anomaly_type")
    search_fields = ("metric_type", "anomaly_type")
    readonly_fields = ("detected_at",)


@admin.register(PlatformIncident, site=platform_admin_site)
class PlatformIncidentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "severity",
        "status",
        "incident_type",
        "source_system",
        "affected_school",
        "detected_at",
    )
    list_filter = ("severity", "status", "incident_type", "source_system")
    search_fields = (
        "title",
        "summary",
        "affected_schema_name",
        "affected_school__name",
    )
    readonly_fields = (
        "detected_at",
        "created_at",
        "updated_at",
        "acknowledged_at",
        "resolved_at",
    )
    raw_id_fields = ("affected_school",)
