from django.contrib import admin
from django.utils.html import format_html

from config.admin import register_both, register_platform_admin
from unfold.admin import ModelAdmin

from .models import (
    BrandProfile,
    BrandSettings,
    DesignTemplate,
    GlobalBrandRegistry,
    PlatformGlobalBranding,
    ThemePack,
)


class ProxyOwnerAdmin(ModelAdmin):
    list_display = ("record_key", "proxy_owner_label")

    @admin.display(description="PK")
    def record_key(self, obj):
        return obj.pk

    @admin.display(description="Record")
    def proxy_owner_label(self, obj):
        return str(obj)


class ThemePackAdmin(ModelAdmin):
    change_form_template = "admin/siteconfig/themepack/change_form.html"
    list_display = ("name", "is_active", "is_default", "layout", "palette_preview")
    list_filter = ("is_active", "layout")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name", "slug")
    fieldsets = (
        (
            "Color Picker",
            {
                "description": "Searching for that perfect color? Use our hex color picker to browse millions of colors and harmonies, and export Hex, RGB, HSL and OKLCH codes.",
                "fields": ("primary_color", "accent_color", "background_color"),
            },
        ),
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "description",
                    "font_family",
                    "layout",
                    "palette",
                )
            },
        ),
        (
            "Assets",
            {
                "fields": (
                    "logo",
                    "background_image",
                    "video_background",
                    "svg_background",
                    "logo_opacity",
                    "logo_background_mode",
                )
            },
        ),
        (
            "Options",
            {
                "fields": (
                    "applies_to_admin",
                    "backend_console_theme",
                    "is_active",
                    "is_default",
                    "custom_css",
                )
            },
        ),
    )

    def palette_preview(self, obj):
        start, end = obj.gradient_colors
        # Keep the native table CSP-clean. The former inline gradient was
        # blocked by the production style-src policy, leaving an empty cell.
        return format_html("<span>{} → {}</span>", start, end)

    palette_preview.short_description = "Gradient"


register_both(ThemePack, ThemePackAdmin)

for model in (DesignTemplate, BrandProfile, BrandSettings):
    register_both(model, ProxyOwnerAdmin)

register_platform_admin(GlobalBrandRegistry, ProxyOwnerAdmin)


class PlatformGlobalBrandingAdmin(ModelAdmin):
    """Singleton platform branding (Phase B Batch 3 primary store for media + theme/report FKs)."""

    list_display = ("id", "updated_at")
    readonly_fields = ("id", "updated_at")
    fieldsets = (
        (
            "Media",
            {
                "fields": (
                    "video_background",
                    "svg_background",
                    "logo",
                    "background_image",
                    "favicon",
                    "sidebar_icon",
                )
            },
        ),
        (
            "Theme packs",
            {
                "fields": (
                    "theme_pack",
                    "admin_theme_pack",
                    "teacher_theme_pack",
                    "parent_theme_pack",
                )
            },
        ),
        (
            "Report styles",
            {
                "fields": (
                    "default_term_report_style",
                    "default_annual_report_style",
                )
            },
        ),
        ("Metadata", {"fields": ("id", "updated_at")}),
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


register_platform_admin(PlatformGlobalBranding, PlatformGlobalBrandingAdmin)
