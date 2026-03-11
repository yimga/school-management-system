from django.contrib import admin

from config.admin import register_tenant_admin
from .models import APIAuditLog, APIKey, APIQuota


class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "key_prefix", "school", "created_by", "created_at", "last_used_at", "revoked_at")
    list_filter = ("revoked_at", "created_at")
    search_fields = ("name", "key_prefix")
    readonly_fields = ("key_prefix", "secret_hash", "created_at", "last_used_at", "revoked_at")


class APIAuditLogAdmin(admin.ModelAdmin):
    list_display = ("integration", "action", "changed_by", "reason_short", "ip_address", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("reason", "integration__slug", "integration__name")
    readonly_fields = ("integration", "changed_by", "action", "reason", "ip_address", "created_at")

    def reason_short(self, obj):
        return (obj.reason or "")[:50] + "…" if len(obj.reason or "") > 50 else (obj.reason or "—")

    reason_short.short_description = "Reason"


class APIQuotaAdmin(admin.ModelAdmin):
    list_display = ("quota_type", "school", "limit_value", "period_minutes")
    list_filter = ("quota_type",)


register_tenant_admin(APIKey, APIKeyAdmin)
register_tenant_admin(APIQuota, APIQuotaAdmin)
register_tenant_admin(APIAuditLog, APIAuditLogAdmin)
