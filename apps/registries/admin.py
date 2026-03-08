from django.contrib import admin

from config.admin import admin_site

from .models import (
    AcademicTerminologyRegistry,
    CalendarSystemRegistry,
    CountryRegistry,
    CurrencyRegistry,
    DocumentTypeRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    FeeCategoryRegistry,
    GradeScaleRegistry,
    InstitutionTypeRegistry,
    LocaleRegistry,
    SubdivisionRegistry,
    TimeZoneRegistry,
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


@admin.register(TimeZoneRegistry, site=admin_site)
class TimeZoneRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "utc_offset", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(CurrencyRegistry, site=admin_site)
class CurrencyRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "decimal_places", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "symbol")


@admin.register(LocaleRegistry, site=admin_site)
class LocaleRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_rtl", "sort_order", "is_active")
    list_filter = ("is_active", "is_rtl")
    search_fields = ("code", "name")


@admin.register(CalendarSystemRegistry, site=admin_site)
class CalendarSystemRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country_code", "term_count_per_year", "sort_order", "is_active")
    list_filter = ("is_active", "country_code")
    search_fields = ("code", "name")


@admin.register(InstitutionTypeRegistry, site=admin_site)
class InstitutionTypeRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(AcademicTerminologyRegistry, site=admin_site)
class AcademicTerminologyRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country_code", "sort_order", "is_active")
    list_filter = ("is_active", "country_code")
    search_fields = ("code", "name")


@admin.register(DocumentTypeRegistry, site=admin_site)
class DocumentTypeRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "country_code", "sort_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("code", "name")


@admin.register(FeeCategoryRegistry, site=admin_site)
class FeeCategoryRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "country_code", "sort_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("code", "name")


@admin.register(GradeScaleRegistry, site=admin_site)
class GradeScaleRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "family", "country_code", "sort_order", "is_active")
    list_filter = ("is_active", "family")
    search_fields = ("code", "name")
