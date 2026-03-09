"""
Admin configuration for automation models.
"""
from django.contrib import admin
from config.admin import platform_admin_site
from unfold.admin import ModelAdmin
from .models import AutomationExecutionLog, AutomationApprovalQueue, MigrationProfile, MigrationRun


@admin.register(AutomationExecutionLog, site=platform_admin_site)
class AutomationExecutionLogAdmin(ModelAdmin):
    list_display = ("task_name", "school", "schema_name", "execution_type", "status", "records_processed", "records_failed", "started_at", "completed_at")
    list_filter = ("school", "task_name", "execution_type", "status", "started_at")
    date_hierarchy = "started_at"
    search_fields = ("task_name", "schema_name", "error_message")
    readonly_fields = ("started_at", "completed_at", "execution_summary")
    list_per_page = 50
    show_full_result_count = False
    
    fieldsets = (
        ("Execution Info", {
            "fields": ("task_name", "school", "schema_name", "execution_type", "status", "triggered_by")
        }),
        ("Timing", {
            "fields": ("started_at", "completed_at")
        }),
        ("Results", {
            "fields": ("records_processed", "records_failed", "error_message", "execution_summary")
        }),
    )


@admin.register(AutomationApprovalQueue, site=platform_admin_site)
class AutomationApprovalQueueAdmin(ModelAdmin):
    list_display = ("automation_type", "school", "schema_name", "status", "requested_by", "approved_by", "created_at", "approved_at")
    list_filter = ("school", "automation_type", "status", "created_at")
    search_fields = ("automation_type", "schema_name", "rejection_reason")
    readonly_fields = ("created_at", "execution_summary", "execution_log")
    list_per_page = 50
    show_full_result_count = False
    
    fieldsets = (
        ("Request Info", {
            "fields": ("automation_type", "school", "schema_name", "status", "requested_by")
        }),
        ("Approval", {
            "fields": ("approved_by", "approved_at", "rejection_reason")
        }),
        ("Details", {
            "fields": ("execution_summary", "execution_log", "created_at")
        }),
    )
    
    actions = ["approve_selected", "reject_selected"]
    
    def approve_selected(self, request, queryset):
        """Approve selected automation requests."""
        count = 0
        for queue_entry in queryset.filter(status=AutomationApprovalQueue.Status.PENDING):
            queue_entry.approve(request.user)
            count += 1
        self.message_user(request, f"Approved {count} automation request(s).")
    approve_selected.short_description = "Approve selected automation requests"
    
    def reject_selected(self, request, queryset):
        """Reject selected automation requests."""
        count = 0
        for queue_entry in queryset.filter(status=AutomationApprovalQueue.Status.PENDING):
            queue_entry.reject(request.user, "Bulk rejection")
            count += 1
        self.message_user(request, f"Rejected {count} automation request(s).")
    reject_selected.short_description = "Reject selected automation requests"


@admin.register(MigrationProfile, site=platform_admin_site)
class MigrationProfileAdmin(ModelAdmin):
    list_display = ("slug", "name", "source_system", "format", "domain", "is_active", "sort_order")
    list_filter = ("format", "domain", "source_system", "is_active")
    search_fields = ("slug", "name", "description")
    ordering = ("sort_order", "slug")


@admin.register(MigrationRun, site=platform_admin_site)
class MigrationRunAdmin(ModelAdmin):
    list_display = (
        "migration_type",
        "school",
        "dry_run",
        "status",
        "row_count",
        "created_count",
        "updated_count",
        "error_count",
        "can_rollback_display",
        "started_at",
        "triggered_by",
    )
    list_filter = ("migration_type", "dry_run", "status", "school")
    date_hierarchy = "started_at"
    search_fields = ("migration_type", "error_message")
    readonly_fields = ("started_at", "completed_at", "execution_summary", "row_count", "rollback_snapshot", "rolled_back_by_run")
    list_per_page = 50
    actions = ["trigger_rollback_action"]

    def can_rollback_display(self, obj):
        if obj.migration_type == "rollback":
            return "—"
        return "Yes" if obj.can_rollback else "No"
    can_rollback_display.short_description = "Can rollback"

    def trigger_rollback_action(self, request, queryset):
        runs = [r for r in queryset if r.can_rollback]
        if not runs:
            self.message_user(request, "No selected run can be rolled back (dry-run, already rolled back, or no snapshot).", level=40)
            return
        for run in runs[:1]:  # one at a time
            rollback_run, result = run.trigger_rollback(user=request.user)
            if result.get("success"):
                self.message_user(request, f"Rollback created: run #{rollback_run.pk}. {result.get('message', '')} Reverted: {result.get('reverted_count', 0)}.")
            else:
                self.message_user(request, f"Rollback failed: {result.get('message', '')}", level=40)
            break
        if len(runs) > 1:
            self.message_user(request, "Only the first eligible run was rolled back. Select one run to roll back another.", level=30)
    trigger_rollback_action.short_description = "Trigger rollback for selected run"
