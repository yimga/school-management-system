from django.contrib import admin

from config.admin import register_both, register_platform_admin

from .models import BrandProfile, BrandSettings, DesignTemplate, GlobalBrandRegistry, ThemePack


class ProxyOwnerAdmin(admin.ModelAdmin):
    list_display = ("record_key", "proxy_owner_label")

    @admin.display(description="PK")
    def record_key(self, obj):
        return obj.pk

    @admin.display(description="Record")
    def proxy_owner_label(self, obj):
        return str(obj)


for model in (ThemePack, DesignTemplate, BrandProfile, BrandSettings):
    register_both(model, ProxyOwnerAdmin)

register_platform_admin(GlobalBrandRegistry, ProxyOwnerAdmin)
