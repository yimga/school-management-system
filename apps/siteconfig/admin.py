from django.contrib import admin

from unfold.admin import ModelAdmin
from django.utils.html import format_html

from .models import Integration, ReportTemplate, SiteSettings, ThemePack, UserPreference


# ==========================
# SITE CUSTOMIZER (CORE)
# ==========================
@admin.register(SiteSettings)
class SiteSettingsAdmin(ModelAdmin):
    """
    Main Site Customizer UI.
    Enforces a single settings row and groups options cleanly.
    """

    # Only allow ONE row
    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    readonly_fields = ("updated_at", "logo_preview")

    fieldsets = (
        ("Branding", {
            "fields": (
                "site_name",
                "tagline",
                "logo",
                "logo_preview",
                "background_image",
                "brand_font",
                "custom_css",
                "theme_pack",
            )
        }),
        ("Company Details", {
            "fields": (
                "company_name",
                "company_slug",
                "school_code",
                "company_address",
                "company_phone",
                "company_email",
                "ministry_registration_code",
            )
        }),
        ("Theme & Experience", {
            "fields": (
                "primary_color",
                "accent_color",
                "use_dark_mode",
                "report_downloads_enabled",
                "default_dashboard_view",
                "default_refresh_rate",
            )
        }),
        ("System Behavior", {
            "fields": (
                "maintenance_mode",
            )
        }),
        ("Feature Toggles (Modules)", {
            "fields": (
                "enable_parent_portal",
                "enable_teacher_portal",
                "enable_reports_pdf",
                "portal_features",
            )
        }),
        ("Notifications & Analytics", {
            "fields": (
                "notification_channels",
            )
        }),
        ("Compliance & Payroll", {
            "fields": (
                "compliance_profile",
            )
        }),
        ("Analytics Defaults", {
            "fields": (
                "top_students_default_limit",
                "pass_mark",
                "use_promotion_rule_for_pass",
                "weak_subject_threshold",
                "improvement_delta_threshold",
                "deadline_mode",
            )
        }),
        ("Metadata", {
            "fields": ("updated_at",),
        }),
    )

    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="height:60px;border-radius:12px;background:#fff;padding:6px;" />',
                obj.logo.url,
            )
        return "No logo uploaded"

    logo_preview.short_description = "Logo Preview"


@admin.register(ThemePack)
class ThemePackAdmin(ModelAdmin):
    list_display = ("name", "is_active", "is_default", "layout")
    list_filter = ("is_active", "layout")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")


@admin.register(UserPreference)
class UserPreferenceAdmin(ModelAdmin):
    list_display = ("user", "dashboard_view", "timezone", "refresh_rate_minutes")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ReportTemplate)
class ReportTemplateAdmin(ModelAdmin):
    list_display = ("name", "slug", "preferred_format", "is_active", "updated_at")
    list_filter = ("preferred_format", "is_active")
    search_fields = ("name", "slug")
    readonly_fields = ("created_at", "updated_at")


# ==========================
# INTEGRATIONS / PLUGINS
# ==========================
@admin.register(Integration)
class IntegrationAdmin(ModelAdmin):
    """
    Plugin / API Integrations manager.
    Examples: Email, SMS, Payments, Analytics.
    """

    list_display = (
        "name",
        "provider",
        "enabled",
        "updated_at",
    )

    list_filter = (
        "provider",
        "enabled",
    )

    search_fields = (
        "name",
        "provider",
    )

    ordering = ("provider", "name")

