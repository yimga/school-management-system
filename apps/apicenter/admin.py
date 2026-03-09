from django.contrib import admin

from config.admin import register_tenant_admin
from .models import APIAuditLog


class APIAuditLogAdmin(admin.ModelAdmin):
    list_display = ("integration", "action", "changed_by", "reason_short", "ip_address", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("reason", "integration__slug", "integration__name")
    readonly_fields = ("integration", "changed_by", "action", "reason", "ip_address", "created_at")

    def reason_short(self, obj):
        return (obj.reason or "")[:50] + "…" if len(obj.reason or "") > 50 else (obj.reason or "—")

    reason_short.short_description = "Reason"


register_tenant_admin(APIAuditLog, APIAuditLogAdmin)
