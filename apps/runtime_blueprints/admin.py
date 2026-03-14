from django.contrib import admin

from config.admin import register_both, register_platform_admin, register_tenant_admin

from .models import (
    BlueprintCompatibilityRule,
    BlueprintPack,
    DashboardLayout,
    DashboardPack,
    DashboardPackAssignment,
    DashboardTemplate,
    DashboardUserPreference,
    DashboardWidget,
    FormDraft,
    SuperAdminDashboardPreference,
    TenantBlueprint,
    TenantLayoutAssignment,
    TenantWorkflow,
    WorkflowPack,
    WorkflowPackAssignment,
    WorkflowTemplate,
)


class ProxyOwnerAdmin(admin.ModelAdmin):
    list_display = ("record_key", "proxy_owner_label")

    @admin.display(description="PK")
    def record_key(self, obj):
        return obj.pk

    @admin.display(description="Record")
    def proxy_owner_label(self, obj):
        return str(obj)


for model in (
    BlueprintPack,
    BlueprintCompatibilityRule,
    TenantBlueprint,
    FormDraft,
):
    register_platform_admin(model, ProxyOwnerAdmin)

for model in (
    DashboardLayout,
    DashboardPack,
    DashboardPackAssignment,
    DashboardTemplate,
    DashboardWidget,
    WorkflowPack,
    WorkflowPackAssignment,
    WorkflowTemplate,
):
    register_both(model, ProxyOwnerAdmin)

for model in (DashboardUserPreference, TenantLayoutAssignment, TenantWorkflow):
    register_tenant_admin(model, ProxyOwnerAdmin)

register_platform_admin(SuperAdminDashboardPreference, ProxyOwnerAdmin)
