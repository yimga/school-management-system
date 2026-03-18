from django.contrib import admin

from config.admin import register_both, register_platform_admin, register_tenant_admin

from .models import (
    EducationSystemProfile,
    GradingScaleConfig,
    HolidayCalendar,
    Province,
    RegionConfig,
    SystemFeature,
    TenantSystem,
    WeatherLocation,
)


class ProxyOwnerAdmin(admin.ModelAdmin):
    list_display = ("record_key", "proxy_owner_label")

    @admin.display(description="PK")
    def record_key(self, obj):
        return obj.pk

    @admin.display(description="Record")
    def proxy_owner_label(self, obj):
        return str(obj)


for model in (
    RegionConfig,
    EducationSystemProfile,
    Province,
    SystemFeature,
    TenantSystem,
):
    register_platform_admin(model, ProxyOwnerAdmin)

for model in (GradingScaleConfig, WeatherLocation):
    register_both(model, ProxyOwnerAdmin)

register_tenant_admin(HolidayCalendar, ProxyOwnerAdmin)
