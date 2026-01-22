"""
Compliance admin interface for Phase 4: comprehensive audit trail and reporting.
Enables visibility and control over all system actions and access patterns.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin
from .models_audit import AuditLog, UserActivitySession, AccessLog, ComplianceReport


@admin.register(AuditLog)
class AuditLogAdmin(ModelAdmin):
    list_display = ("timestamp", "user", "action", "model_name", "object_repr", "sensitivity", "ip_address")
    list_filter = ("action", "sensitivity", "model_name", "app_label", "timestamp")
    search_fields = ("user__username", "object_id", "object_repr", "reason")
    readonly_fields = ("timestamp", "ip_address", "user_agent", "old_values", "new_values", "changed_fields")
    list_per_page = 100
    date_hierarchy = "timestamp"

    fieldsets = (
        ("Action", {"fields": ("action", "reason")}),
        ("Subject", {"fields": ("model_name", "object_id", "object_repr", "app_label")}),
        ("Actor", {"fields": ("user", "ip_address", "user_agent")}),
        ("Data", {
            "fields": ("old_values", "new_values", "changed_fields"),
            "classes": ("collapse",),
            "description": "Change details (collapsed for readability)"
        }),
        ("Classification", {"fields": ("sensitivity",)}),
        ("Metadata", {"fields": ("timestamp",), "classes": ("collapse",)}),
    )

    def has_add_permission(self, request):
        """Prevent manual audit log creation."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Prevent deletion of audit logs."""
        return False


@admin.register(UserActivitySession)
class UserActivitySessionAdmin(ModelAdmin):
    list_display = ("user", "login_timestamp", "logout_timestamp", "ip_address", "page_views", "api_calls", "is_suspicious")
    list_filter = ("is_suspicious", "login_timestamp")
    search_fields = ("user__username", "ip_address")
    readonly_fields = ("session_key", "login_timestamp", "logout_timestamp", "last_activity")
    list_per_page = 100
    date_hierarchy = "login_timestamp"

    fieldsets = (
        ("Session", {"fields": ("session_key", "user", "login_timestamp", "logout_timestamp", "last_activity")}),
        ("Network", {"fields": ("ip_address", "user_agent")}),
        ("Activity", {"fields": ("page_views", "api_calls")}),
        ("Security", {"fields": ("is_suspicious", "notes")}),
    )


@admin.register(AccessLog)
class AccessLogAdmin(ModelAdmin):
    list_display = ("timestamp", "user", "access_type", "resource", "status", "response_time_ms", "ip_address")
    list_filter = ("access_type", "status", "request_method", "timestamp")
    search_fields = ("user__username", "resource", "ip_address")
    readonly_fields = ("timestamp", "response_time_ms")
    list_per_page = 100
    date_hierarchy = "timestamp"

    fieldsets = (
        ("Request", {"fields": ("access_type", "resource", "request_method")}),
        ("Response", {"fields": ("status", "response_time_ms", "error_message")}),
        ("Actor", {"fields": ("user", "ip_address")}),
        ("Metadata", {"fields": ("timestamp",)}),
    )


@admin.register(ComplianceReport)
class ComplianceReportAdmin(ModelAdmin):
    list_display = ("report_type", "start_date", "end_date", "generated_at", "generated_by")
    list_filter = ("report_type", "generated_at")
    search_fields = ("generated_by__username",)
    readonly_fields = ("generated_at", "summary", "details", "issues", "export_formats")
    list_per_page = 50
    date_hierarchy = "generated_at"

    fieldsets = (
        ("Report", {"fields": ("report_type", "start_date", "end_date")}),
        ("Generation", {"fields": ("generated_at", "generated_by")}),
        ("Results", {
            "fields": ("summary", "details", "issues", "export_formats"),
            "classes": ("collapse",),
        }),
    )

    def has_add_permission(self, request):
        """Prevent manual report creation (use management command instead)."""
        return False
