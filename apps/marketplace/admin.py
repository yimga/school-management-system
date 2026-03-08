from django.contrib import admin
from .models import (
    PublisherOrganization,
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceReview,
    AppScope,
    AppInstallation,
    ScopeGrant,
    AppBillingLedger,
    AppAuditLog,
    AppVersionCompat,
    CapabilityRegistry,
)


@admin.register(PublisherOrganization)
class PublisherOrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "verification_status", "country_code", "payout_processor_code")
    list_filter = ("verification_status", "country_code", "payout_processor_code")
    search_fields = ("name", "legal_name", "slug", "payout_ref")


@admin.register(MarketplaceApp)
class MarketplaceAppAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "publisher", "kind", "version", "is_active", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("slug", "name", "publisher__name")


@admin.register(MarketplaceListing)
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
    list_filter = ("status", "security_review_status", "certification_status", "kill_switch_active")
    search_fields = ("app__slug", "app__name", "publisher__name")
    raw_id_fields = ("app", "publisher", "approved_by")


@admin.register(MarketplaceReview)
class MarketplaceReviewAdmin(admin.ModelAdmin):
    list_display = ("listing", "review_type", "status", "app_version", "requested_at", "reviewed_at")
    list_filter = ("review_type", "status")
    search_fields = ("listing__app__slug", "listing__app__name", "listing__publisher__name")
    raw_id_fields = ("listing", "requested_by", "reviewed_by")


@admin.register(AppScope)
class AppScopeAdmin(admin.ModelAdmin):
    list_display = ("app", "scope_code", "sensitive", "description")
    list_filter = ("app", "sensitive")


@admin.register(CapabilityRegistry)
class CapabilityRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("code", "name", "description")


@admin.register(AppInstallation)
class AppInstallationAdmin(admin.ModelAdmin):
    list_display = ("app", "school", "status", "installed_at", "installed_by")
    list_filter = ("status", "app")
    search_fields = ("school__slug", "app__slug")
    raw_id_fields = ("school", "installed_by")


@admin.register(ScopeGrant)
class ScopeGrantAdmin(admin.ModelAdmin):
    list_display = ("installation", "scope", "status", "elevated_approved_at", "elevated_approved_by", "granted_at", "granted_by")
    list_filter = ("status",)
    raw_id_fields = ("installation", "scope", "granted_by", "elevated_approved_by")


@admin.register(AppBillingLedger)
class AppBillingLedgerAdmin(admin.ModelAdmin):
    list_display = ("app", "school", "kind", "amount", "currency", "created_at")
    list_filter = ("kind", "currency")
    raw_id_fields = ("school", "app", "installation")


@admin.register(AppAuditLog)
class AppAuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "app", "school", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("action",)
    raw_id_fields = ("installation", "school", "app", "actor")
    readonly_fields = ("created_at",)


@admin.register(AppVersionCompat)
class AppVersionCompatAdmin(admin.ModelAdmin):
    list_display = ("app", "platform_min_version", "app_version_min", "app_version_max")
