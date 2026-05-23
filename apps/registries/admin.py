from django import forms
from django.contrib import admin

from config.admin import platform_admin_site

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


class CountryRegistryAdminForm(forms.ModelForm):
    """Wave 8/10 (v3.62.10 — 2026-05-22) — operator-friendly cockpit override.

    Validates that ``cockpit_override_payload`` is a dict and the top-level
    keys belong to the country-pack contract. Surfaces a JSON-shape error
    INSIDE the form (so operators see "calendar_systems must be a list"
    instead of staring at a HTTP 500). Empty / null / "{}" all accepted.
    """

    _ALLOWED_KEYS = {
        "calendar_systems",
        "school_types",
        "education_levels",
        "terminology",
        "languages",
        "writing_direction",
        "system_name",
    }

    class Meta:
        model = CountryRegistry
        fields = "__all__"

    def clean_cockpit_override_payload(self):
        value = self.cleaned_data.get("cockpit_override_payload")
        if value in (None, "", {}):
            return {}
        if not isinstance(value, dict):
            raise forms.ValidationError(
                "Override must be a JSON object (dict), e.g. "
                '{"terminology": {"teacher": "Tuteur"}}.'
            )
        unknown = set(value.keys()) - self._ALLOWED_KEYS
        if unknown:
            raise forms.ValidationError(
                "Unknown override keys: "
                f"{', '.join(sorted(unknown))}. "
                f"Allowed: {', '.join(sorted(self._ALLOWED_KEYS))}."
            )
        # Shape checks per known key.
        for k in ("calendar_systems", "school_types", "education_levels", "languages"):
            if k in value and not isinstance(value[k], list):
                raise forms.ValidationError(
                    f"`{k}` override must be a list (each entry a dict)."
                )
        if "terminology" in value and not isinstance(value["terminology"], dict):
            raise forms.ValidationError(
                "`terminology` override must be a dict (e.g. "
                '{"teacher": "Tuteur"}).'
            )
        return value

    def save(self, commit=True):
        """After save, evict the country_localization service cache so the
        edit takes effect immediately without a process restart."""
        instance = super().save(commit=commit)
        try:
            from apps.siteconfig.country_localization_service import clear_cache
            clear_cache()
        except Exception:  # noqa: BLE001 — admin save must never break on cache evict
            pass
        return instance


@admin.register(CountryRegistry, site=platform_admin_site)
class CountryRegistryAdmin(admin.ModelAdmin):
    form = CountryRegistryAdminForm
    list_display = (
        "code",
        "alpha3_code",
        "name",
        "default_language",
        "default_currency",
        "writing_direction",
        "has_override",
        "is_active",
    )
    list_filter = ("is_active", "default_language", "default_currency", "writing_direction")
    search_fields = ("code", "alpha3_code", "name")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        (None, {
            "fields": ("code", "alpha3_code", "name", "is_active"),
        }),
        ("Display defaults", {
            "fields": (
                "default_language", "default_currency", "default_timezone",
                "writing_direction", "default_calendar_family",
                "default_terminology_pack",
            ),
        }),
        ("Operator overrides (Wave 8/10)", {
            "description": (
                "JSON overlay applied on top of the in-memory country seed "
                "pack at the service hot path. Allowed top-level keys: "
                "calendar_systems (list), school_types (list), education_levels "
                "(list), languages (list), terminology (dict), writing_direction "
                "(str), system_name (str). Lists override wholesale; dicts merge "
                "one level deep. Empty / blank = no override."
            ),
            "classes": ("collapse",),
            "fields": ("cockpit_override_payload",),
        }),
        ("Registry metadata", {
            "classes": ("collapse",),
            "fields": ("labels", "metadata", "created_at", "updated_at"),
        }),
    )

    def has_override(self, obj) -> bool:
        return bool(getattr(obj, "cockpit_override_payload", None) or {})
    has_override.boolean = True
    has_override.short_description = "Override"


@admin.register(SubdivisionRegistry, site=platform_admin_site)
class SubdivisionRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country", "subdivision_type", "is_active")
    list_filter = ("country", "subdivision_type", "is_active")
    search_fields = ("code", "name", "country__name", "country__code")


@admin.register(EducationLevelRegistry, site=platform_admin_site)
class EducationLevelRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "global_name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "global_name")


@admin.register(EducationSystemTypeRegistry, site=platform_admin_site)
class EducationSystemTypeRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "sort_order", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("code", "name", "category")


@admin.register(TimeZoneRegistry, site=platform_admin_site)
class TimeZoneRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "utc_offset", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(CurrencyRegistry, site=platform_admin_site)
class CurrencyRegistryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "symbol",
        "decimal_places",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "name", "symbol")


@admin.register(LocaleRegistry, site=platform_admin_site)
class LocaleRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_rtl", "sort_order", "is_active")
    list_filter = ("is_active", "is_rtl")
    search_fields = ("code", "name")


@admin.register(CalendarSystemRegistry, site=platform_admin_site)
class CalendarSystemRegistryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "country_code",
        "term_count_per_year",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active", "country_code")
    search_fields = ("code", "name")


@admin.register(InstitutionTypeRegistry, site=platform_admin_site)
class InstitutionTypeRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(AcademicTerminologyRegistry, site=platform_admin_site)
class AcademicTerminologyRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country_code", "sort_order", "is_active")
    list_filter = ("is_active", "country_code")
    search_fields = ("code", "name")


@admin.register(DocumentTypeRegistry, site=platform_admin_site)
class DocumentTypeRegistryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "country_code",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active", "category")
    search_fields = ("code", "name")


@admin.register(FeeCategoryRegistry, site=platform_admin_site)
class FeeCategoryRegistryAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "category",
        "country_code",
        "sort_order",
        "is_active",
    )
    list_filter = ("is_active", "category")
    search_fields = ("code", "name")


@admin.register(GradeScaleRegistry, site=platform_admin_site)
class GradeScaleRegistryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "family", "country_code", "sort_order", "is_active")
    list_filter = ("is_active", "family")
    search_fields = ("code", "name")
