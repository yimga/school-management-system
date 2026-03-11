from django.contrib import admin
from .models import ProcessDefinition, OrchestrationRun


@admin.register(ProcessDefinition)
class ProcessDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "created_at")
    search_fields = ("code", "name")


@admin.register(OrchestrationRun)
class OrchestrationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "definition", "school", "status", "retry_count", "created_at", "completed_at")
    list_filter = ("status", "definition")
    search_fields = ("definition__code",)
    raw_id_fields = ("school", "triggered_by")
    readonly_fields = ("created_at", "updated_at")
