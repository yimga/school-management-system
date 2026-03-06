from django.contrib import admin

from config.admin import admin_site

from .models import (
    CountryRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    SubdivisionRegistry,
)


@admin.register(CountryRegistry, site=admin_site)
class CountryRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "alpha3_code", "name", "default_language", "default_currency", "is_active")
    list_filter = ("is_active", "default_language", "default_currency")
    search_fields = ("code", "alpha3_code", "name")


@admin.register(SubdivisionRegistry, site=admin_site)
class SubdivisionRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country", "subdivision_type", "is_active")
    list_filter = ("country", "subdivision_type", "is_active")
    search_fields = ("code", "name", "country__name", "country__code")


@admin.register(EducationLevelRegistry, site=admin_site)
class EducationLevelRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "global_name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "global_name")


@admin.register(EducationSystemTypeRegistry, site=admin_site)
class EducationSystemTypeRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "sort_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("code", "name", "category")
