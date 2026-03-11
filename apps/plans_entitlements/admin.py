from django.contrib import admin

from config.admin import register_platform_admin

from .models import (
    CountryMultiplier,
    Plan,
    PlanAddon,
)


class ProxyOwnerAdmin(admin.ModelAdmin):
    list_display = ("record_key", "proxy_owner_label")

    @admin.display(description="PK")
    def record_key(self, obj):
        return obj.pk

    @admin.display(description="Record")
    def proxy_owner_label(self, obj):
        return str(obj)


for model in (Plan, PlanAddon, CountryMultiplier):
    register_platform_admin(model, ProxyOwnerAdmin)
