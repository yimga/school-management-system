from django.contrib import admin

from config.admin import register_tenant_admin
from .models import AccessRequest, RequestDecision, RequestAudit


class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "school", "schema_name", "request_type", "status", "requester", "requested_at")
    list_filter = ("school", "request_type", "status")
    search_fields = ("reference", "title", "schema_name", "requester__username", "requester__email")
    readonly_fields = ("reference", "requested_at", "updated_at")
    list_per_page = 50
    show_full_result_count = False


class RequestDecisionAdmin(admin.ModelAdmin):
    list_display = ("request", "decision", "decided_by", "created_at")
    list_filter = ("decision",)
    search_fields = ("request__reference", "decided_by__username")
    readonly_fields = ("created_at",)
    list_per_page = 50
    show_full_result_count = False


class RequestAuditAdmin(admin.ModelAdmin):
    list_display = ("request", "action", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("request__reference", "actor__username", "message")
    readonly_fields = ("created_at",)
    list_per_page = 50
    show_full_result_count = False


register_tenant_admin(AccessRequest, AccessRequestAdmin)
register_tenant_admin(RequestDecision, RequestDecisionAdmin)
register_tenant_admin(RequestAudit, RequestAuditAdmin)
