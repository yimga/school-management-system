from django.contrib import admin
from config.admin import platform_admin_site
from .models import (
    PublisherOrganization,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    AppPermissionScope,
    AppScope,
    AppInstallation,
    ScopeGrant,
    AppBillingLedger,
    AppAuditLog,
    AppVersionCompat,
    CapabilityRegistry,
)


@admin.register(PublisherOrganization, site=platform_admin_site)
class PublisherOrganizationAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "verification_status",
        "country_code",
        "payout_processor_code",
    )
    list_filter = ("verification_status", "country_code", "payout_processor_code")
    search_fields = ("name", "legal_name", "slug", "payout_ref")


@admin.register(AppPermissionScope, site=platform_admin_site)
class AppPermissionScopeAdmin(admin.ModelAdmin):
    list_display = ("code", "domain", "access", "description")
    search_fields = ("code", "domain", "description")


@admin.register(MarketplaceApp, site=platform_admin_site)
class MarketplaceAppAdmin(admin.ModelAdmin):
    list_display = (
        "slug",
        "name",
        "publisher",
        "kind",
        "pricing_model",
        "is_intentionally_free",
        "price",
        "billing_interval",
        "version",
        "is_active",
        "updated_at",
    )
    list_filter = ("kind", "is_active", "pricing_model", "billing_interval", "is_intentionally_free")
    search_fields = ("slug", "name", "publisher__name")

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(MarketplaceListing, site=platform_admin_site)
class MarketplaceListingAdmin(admin.ModelAdmin):
    list_display = (
        "app",
        "publisher",
        "status",
        "security_review_status",
        "certification_status",
        "kill_switch_active",
        "revenue_share_percent",
    )
    list_filter = (
        "status",
        "security_review_status",
        "certification_status",
        "kill_switch_active",
    )
    search_fields = ("app__slug", "app__name", "publisher__name")
    raw_id_fields = ("app", "publisher", "approved_by")


@admin.register(MarketplaceReview, site=platform_admin_site)
class MarketplaceReviewAdmin(admin.ModelAdmin):
    list_display = (
        "listing",
        "review_type",
        "status",
        "app_version",
        "requested_at",
        "reviewed_at",
    )
    list_filter = ("review_type", "status")
    search_fields = (
        "listing__app__slug",
        "listing__app__name",
        "listing__publisher__name",
    )
    raw_id_fields = ("listing", "requested_by", "reviewed_by")


@admin.register(AppScope, site=platform_admin_site)
class AppScopeAdmin(admin.ModelAdmin):
    list_display = ("app", "scope_code", "sensitive", "description")
    list_filter = ("app", "sensitive")


@admin.register(CapabilityRegistry, site=platform_admin_site)
class CapabilityRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("code", "name", "description")


@admin.register(AppInstallation, site=platform_admin_site)
class AppInstallationAdmin(admin.ModelAdmin):
    list_display = ("app", "school", "status", "installed_at", "installed_by")
    list_filter = ("status", "app")
    search_fields = ("school__slug", "app__slug")
    raw_id_fields = ("school", "installed_by")


@admin.register(ScopeGrant, site=platform_admin_site)
class ScopeGrantAdmin(admin.ModelAdmin):
    list_display = (
        "installation",
        "scope",
        "status",
        "elevated_approved_at",
        "elevated_approved_by",
        "granted_at",
        "granted_by",
    )
    list_filter = ("status",)
    raw_id_fields = ("installation", "scope", "granted_by", "elevated_approved_by")


@admin.register(AppBillingLedger, site=platform_admin_site)
class AppBillingLedgerAdmin(admin.ModelAdmin):
    list_display = ("app", "school", "kind", "amount", "currency", "created_at")
    list_filter = ("kind", "currency")
    raw_id_fields = ("school", "app", "installation")


@admin.register(AppAuditLog, site=platform_admin_site)
class AppAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "app", "school", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("action",)
    raw_id_fields = ("installation", "school", "app", "actor")
    readonly_fields = ("created_at",)


@admin.register(AppVersionCompat, site=platform_admin_site)
class AppVersionCompatAdmin(admin.ModelAdmin):
    list_display = ("app", "platform_min_version", "app_version_min", "app_version_max")
