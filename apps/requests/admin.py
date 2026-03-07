from django.contrib import admin

from config.admin import admin_site
from .models import AccessRequest, RequestDecision, RequestAudit


@admin.register(AccessRequest, site=admin_site)
class AccessRequestAdmin(admin.ModelAdmin):
    list_display = ("reference", "school", "schema_name", "request_type", "status", "requester", "requested_at")
    list_filter = ("school", "request_type", "status")
    search_fields = ("reference", "title", "schema_name", "requester__username", "requester__email")
    readonly_fields = ("reference", "requested_at", "updated_at")
    list_per_page = 50
    show_full_result_count = False


@admin.register(RequestDecision, site=admin_site)
class RequestDecisionAdmin(admin.ModelAdmin):
    list_display = ("request", "decision", "decided_by", "created_at")
    list_filter = ("decision",)
    search_fields = ("request__reference", "decided_by__username")
    readonly_fields = ("created_at",)
    list_per_page = 50
    show_full_result_count = False


@admin.register(RequestAudit, site=admin_site)
class RequestAuditAdmin(admin.ModelAdmin):
    list_display = ("request", "action", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("request__reference", "actor__username", "message")
    readonly_fields = ("created_at",)
    list_per_page = 50
    show_full_result_count = False
