from django.contrib import admin

from config.admin import register_both, register_platform_admin, register_tenant_admin

from .models import (
    EducationSystemProfile,
    GradingScaleConfig,
    HolidayCalendar,
    Province,
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


# RegionConfig: platform CRUD is super:regions_list / region_* (not platform /admin/).
for model in (
    EducationSystemProfile,
    Province,
    SystemFeature,
    TenantSystem,
):
    register_platform_admin(model, ProxyOwnerAdmin)

# GradingScaleConfig: catalog CRUD is super:grading_list / grading_*; tenant admin only here.
register_tenant_admin(GradingScaleConfig, ProxyOwnerAdmin)
register_both(WeatherLocation, ProxyOwnerAdmin)

register_tenant_admin(HolidayCalendar, ProxyOwnerAdmin)
