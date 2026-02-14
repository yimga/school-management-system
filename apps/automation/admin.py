"""
Admin configuration for automation models.
"""
from django.contrib import admin
from config.admin import admin_site
from unfold.admin import ModelAdmin
from .models import AutomationExecutionLog, AutomationApprovalQueue


@admin.register(AutomationExecutionLog, site=admin_site)
class AutomationExecutionLogAdmin(ModelAdmin):
    list_display = ("task_name", "execution_type", "status", "records_processed", "records_failed", "started_at", "completed_at")
    list_filter = ("task_name", "execution_type", "status", "started_at")
    date_hierarchy = "started_at"
    search_fields = ("task_name", "error_message")
    readonly_fields = ("started_at", "completed_at", "execution_summary")
    list_per_page = 50
    show_full_result_count = False
    
    fieldsets = (
        ("Execution Info", {
            "fields": ("task_name", "execution_type", "status", "triggered_by")
        }),
        ("Timing", {
            "fields": ("started_at", "completed_at")
        }),
        ("Results", {
            "fields": ("records_processed", "records_failed", "error_message", "execution_summary")
        }),
    )


@admin.register(AutomationApprovalQueue, site=admin_site)
class AutomationApprovalQueueAdmin(ModelAdmin):
    list_display = ("automation_type", "status", "requested_by", "approved_by", "created_at", "approved_at")
    list_filter = ("automation_type", "status", "created_at")
    search_fields = ("automation_type", "rejection_reason")
    readonly_fields = ("created_at", "execution_summary", "execution_log")
    list_per_page = 50
    show_full_result_count = False
    
    fieldsets = (
        ("Request Info", {
            "fields": ("automation_type", "status", "requested_by")
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
