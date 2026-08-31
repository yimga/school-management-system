from django.contrib import admin

from config.admin import register_platform_admin
from .models import (
    OrchestrationRun,
    OrchestrationSLOMetric,
    OrchestrationStepEvent,
    ProcessDefinition,
    ProcessDefinitionVersion,
)


class ProcessDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "created_at")
    search_fields = ("code", "name")


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


class ProcessDefinitionVersionAdmin(admin.ModelAdmin):
    list_display = ("definition", "version_number", "is_current", "published_at")
    list_filter = ("is_current",)
    search_fields = ("definition__code",)
    raw_id_fields = ("definition", "published_by")


class OrchestrationStepEventAdmin(admin.ModelAdmin):
    list_display = ("run", "sequence_number", "event_type", "step_name", "created_at")
    list_filter = ("event_type",)
    search_fields = ("step_name",)
    raw_id_fields = ("run",)
    readonly_fields = ("created_at",)


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


# A bare @admin.register(Model) lands on Django's DEFAULT admin.site, which
# no urlconf in this repo mounts (config/urls, tenant_urls, manager_urls and
# public_urls were all read). The screen was therefore unreachable from any
# host. Registered explicitly below instead.
#
# apps.orchestration is in SHARED_APPS and has no model on either real site,
# so there is no in-app convention to follow. Process definitions, their
# versions, run history, step events and SLO metrics describe the PLATFORM's
# own workflow engine, not one school's records -- OrchestrationRun carries a
# school FK, but a run is meaningless without the definition that produced it
# and definitions are platform-owned. The operator gets the whole app.
register_platform_admin(ProcessDefinition, ProcessDefinitionAdmin)
register_platform_admin(ProcessDefinitionVersion, ProcessDefinitionVersionAdmin)
register_platform_admin(OrchestrationRun, OrchestrationRunAdmin)
register_platform_admin(OrchestrationStepEvent, OrchestrationStepEventAdmin)
register_platform_admin(OrchestrationSLOMetric, OrchestrationSLOMetricAdmin)
