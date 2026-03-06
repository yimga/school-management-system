"""
Admin for Policy Registry v2 models (CountryProfile, PolicyBundle, TenantBlueprint).
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import BlueprintPack, CountryProfile, PolicyBundle, TenantBlueprint


@admin.register(CountryProfile)
class CountryProfileAdmin(admin.ModelAdmin):
    list_display = ("country_code", "name", "currency_code", "timezone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("country_code", "name")


@admin.register(PolicyBundle)
class PolicyBundleAdmin(admin.ModelAdmin):
    list_display = ("id", "school", "name", "version", "applied_pack_version", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    raw_id_fields = ("school", "created_by")


@admin.register(TenantBlueprint)
class TenantBlueprintAdmin(admin.ModelAdmin):
    list_display = ("school", "active_bundle", "applied_pack", "updated_at")
    raw_id_fields = ("school", "active_bundle", "applied_pack")


@admin.register(BlueprintPack)
class BlueprintPackAdmin(admin.ModelAdmin):
    list_display = ("slug", "name", "category", "country_code", "version", "is_active", "updated_at")
    list_filter = ("is_active", "category")
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
    update_bundle_for_schools_needing_update.short_description = "Update bundle for schools needing this version"
