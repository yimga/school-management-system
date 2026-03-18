from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from config.admin import register_both, register_platform_admin
from unfold.admin import ModelAdmin

from .models import (
    BrandProfile,
    BrandSettings,
    DesignTemplate,
    GlobalBrandRegistry,
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

    # Theme packs are managed from Theme & Experience studio; hide standalone model page.
    def has_module_permission(self, request):
        return False

    def get_model_perms(self, request):
        return {}

    def _studio_redirect(self):
        return HttpResponseRedirect(reverse("siteconfig:theme_colors"))

    def changelist_view(self, request, extra_context=None):
        return self._studio_redirect()

    def add_view(self, request, form_url="", extra_context=None):
        return self._studio_redirect()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        return self._studio_redirect()

    def palette_preview(self, obj):
        start, end = obj.gradient_colors
        style = f"background: linear-gradient(135deg, {start}, {end}); width: 160px; height: 36px; border-radius: 12px;"
        return format_html("<div style='{}'></div>", style)

    palette_preview.short_description = "Gradient"


register_both(ThemePack, ThemePackAdmin)

for model in (DesignTemplate, BrandProfile, BrandSettings):
    register_both(model, ProxyOwnerAdmin)

register_platform_admin(GlobalBrandRegistry, ProxyOwnerAdmin)
