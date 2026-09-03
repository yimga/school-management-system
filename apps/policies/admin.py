"""
Admin for Policy Registry v2 models (CountryProfile, PolicyBundle, TenantBlueprint).
"""

from django.contrib import admin
from config.admin import platform_admin_site, tenant_admin_site
from .models import (
    BlueprintPack,
    BlueprintCompatibilityRule,
    CountryProfile,
    PolicyBundle,
    PolicyCompatibilityRule,
    TenantBlueprint,
    TenantPolicyOverride,
    ScheduledPolicyOverride,
)


@admin.register(CountryProfile, site=platform_admin_site)
class CountryProfileAdmin(admin.ModelAdmin):
    list_display = ("country_code", "name", "currency_code", "timezone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("country_code", "name")


@admin.register(PolicyBundle, site=tenant_admin_site)
class PolicyBundleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "school",
        "name",
        "version",
        "applied_pack_version",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name",)
    raw_id_fields = ("school", "created_by")


@admin.register(TenantBlueprint, site=tenant_admin_site)
class TenantBlueprintAdmin(admin.ModelAdmin):
    list_display = ("school", "active_bundle", "applied_pack", "updated_at")
    raw_id_fields = ("school", "active_bundle", "applied_pack")


@admin.register(BlueprintPack, site=platform_admin_site)
class BlueprintPackAdmin(admin.ModelAdmin):
    list_display = (
        "slug",
        "name",
        "category",
        "list_price",
        "is_premium_commercial",
        "country_code",
        "version",
        "is_active",
        "updated_at",
    )
    list_filter = ("is_active", "category", "is_premium_commercial")
    search_fields = ("slug", "name", "description", "category")
    prepopulated_fields = {"slug": ("name",)}
    actions = ["update_bundle_for_schools_needing_update"]

    def update_bundle_for_schools_needing_update(self, request, queryset):
        """Re-apply selected pack(s) to schools that have it applied but older version (11.2)."""
        from .blueprint_services import update_bundle_for_schools

        total = 0
        for pack in queryset:
            updated = update_bundle_for_schools(pack, applied_by=request.user)
            total += len(updated)
        self.message_user(request, f"Updated bundle for {total} school(s).")

    update_bundle_for_schools_needing_update.short_description = (
        "Update bundle for schools needing this version"
    )


@admin.register(BlueprintCompatibilityRule, site=platform_admin_site)
class BlueprintCompatibilityRuleAdmin(admin.ModelAdmin):
    list_display = ("blueprint_pack", "is_active", "created_at")
    list_filter = ("is_active",)
    raw_id_fields = ("blueprint_pack",)


@admin.register(PolicyCompatibilityRule, site=platform_admin_site)
class PolicyCompatibilityRuleAdmin(admin.ModelAdmin):
    list_display = ("policy_bundle", "blueprint_slug", "country_code", "is_active")
    list_filter = ("is_active",)
    raw_id_fields = ("policy_bundle",)


@admin.register(TenantPolicyOverride, site=tenant_admin_site)
class TenantPolicyOverrideAdmin(admin.ModelAdmin):
    list_display = ("school", "policy_key", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("policy_key",)
    raw_id_fields = ("school",)


@admin.register(ScheduledPolicyOverride, site=tenant_admin_site)
class ScheduledPolicyOverrideAdmin(admin.ModelAdmin):
    list_display = ("school", "policy_key", "start_at", "end_at", "is_active")
    list_filter = ("is_active",)
    raw_id_fields = ("school",)
