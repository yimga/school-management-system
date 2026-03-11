from django.contrib import admin

from config.admin import register_both, register_platform_admin

from .models import (
    AppAuditLog,
    AppBillingLedger,
    AppInstallation,
    AppScope,
    AppVersionCompat,
    CapabilityRegistry,
    Integration,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    PublisherOrganization,
    ScopeGrant,
    ServiceIntegration,
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
    AppAuditLog,
    AppBillingLedger,
    AppInstallation,
    AppScope,
    AppVersionCompat,
    CapabilityRegistry,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    PublisherOrganization,
    ScopeGrant,
):
    register_platform_admin(model, ProxyOwnerAdmin)

for model in (Integration, ServiceIntegration):
    register_both(model, ProxyOwnerAdmin)
