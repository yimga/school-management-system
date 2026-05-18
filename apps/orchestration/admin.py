from django.contrib import admin
from .models import (
    OrchestrationRun,
    OrchestrationSLOMetric,
    OrchestrationStepEvent,
    ProcessDefinition,
    ProcessDefinitionVersion,
)


@admin.register(ProcessDefinition)
class ProcessDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "created_at")
    search_fields = ("code", "name")


@admin.register(OrchestrationRun)
class OrchestrationRunAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "definition",
        "school",
        "status",
        "retry_count",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "definition")
    search_fields = ("definition__code",)
    raw_id_fields = ("school", "triggered_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ProcessDefinitionVersion)
class ProcessDefinitionVersionAdmin(admin.ModelAdmin):
    list_display = ("definition", "version_number", "is_current", "published_at")
    list_filter = ("is_current",)
    search_fields = ("definition__code",)
    raw_id_fields = ("definition", "published_by")


@admin.register(OrchestrationStepEvent)
class OrchestrationStepEventAdmin(admin.ModelAdmin):
    list_display = ("run", "sequence_number", "event_type", "step_name", "created_at")
    list_filter = ("event_type",)
    search_fields = ("step_name",)
    raw_id_fields = ("run",)
    readonly_fields = ("created_at",)


@admin.register(OrchestrationSLOMetric)
class OrchestrationSLOMetricAdmin(admin.ModelAdmin):
    list_display = (
        "definition",
        "window_start",
        "runs_total",
        "success_rate",
        "p95_latency_ms",
        "queue_depth_max",
    )
    list_filter = ("definition",)
    raw_id_fields = ("definition",)
    readonly_fields = ("created_at",)
