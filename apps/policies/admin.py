"""
Admin for Policy Registry v2 models (CountryProfile, PolicyBundle, TenantBlueprint).
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import CountryProfile, PolicyBundle, TenantBlueprint


@admin.register(CountryProfile)
class CountryProfileAdmin(admin.ModelAdmin):
    list_display = ("country_code", "name", "currency_code", "timezone", "is_active")
    list_filter = ("is_active",)
    search_fields = ("country_code", "name")


@admin.register(PolicyBundle)
class PolicyBundleAdmin(admin.ModelAdmin):
    list_display = ("id", "school", "name", "version", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    raw_id_fields = ("school", "created_by")


@admin.register(TenantBlueprint)
class TenantBlueprintAdmin(admin.ModelAdmin):
    list_display = ("school", "active_bundle", "updated_at")
    raw_id_fields = ("school", "active_bundle")
