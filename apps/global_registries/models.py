"""
Global registries bounded-context ownership surface.

These proxy-owner models provide a stable registry import layer while current
data is still stored across `apps.registries` and legacy siteconfig models.
"""

from apps.registries.models import (
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
# Import from concrete modules to avoid circular import when compliance (or others)
# loads global_registries before siteconfig.models has finished loading.
from apps.academics.models import HolidayCalendar as LegacyHolidayCalendar
from apps.siteconfig.models_global_experience import (
    GradingScaleConfig as LegacyGradingScaleConfig,
    WeatherLocation as LegacyWeatherLocation,
)
from apps.siteconfig.models_platform_catalog import (
    EducationSystemProfile as LegacyEducationSystemProfile,
    Province as LegacyProvince,
    RegionConfig as LegacyRegionConfig,
    SystemFeature as LegacySystemFeature,
    TenantSystem as LegacyTenantSystem,
)


def _proxy_model(legacy_model, *, app_label: str, doc: str):
    meta = type(
        "Meta",
        (),
        {
            "proxy": True,
            "app_label": app_label,
            "verbose_name": legacy_model._meta.verbose_name,
            "verbose_name_plural": legacy_model._meta.verbose_name_plural,
        },
    )
    return type(
        legacy_model.__name__,
        (legacy_model,),
        {
            "__module__": __name__,
            "__doc__": doc,
            "Meta": meta,
        },
    )


EducationSystemProfile = _proxy_model(
    LegacyEducationSystemProfile,
    app_label="global_registries",
    doc="Global Registries owner surface for education system profiles.",
)
GradingScaleConfig = _proxy_model(
    LegacyGradingScaleConfig,
    app_label="global_registries",
    doc="Global Registries owner surface for grading scale configurations.",
)
HolidayCalendar = _proxy_model(
    LegacyHolidayCalendar,
    app_label="global_registries",
    doc="Global Registries owner surface for holiday calendars.",
)
Province = _proxy_model(
    LegacyProvince,
    app_label="global_registries",
    doc="Global Registries owner surface for province/state registry entries.",
)
RegionConfig = _proxy_model(
    LegacyRegionConfig,
    app_label="global_registries",
    doc="Global Registries owner surface for region configuration.",
)
SystemFeature = _proxy_model(
    LegacySystemFeature,
    app_label="global_registries",
    doc="Global Registries owner surface for system feature registry data.",
)
TenantSystem = _proxy_model(
    LegacyTenantSystem,
    app_label="global_registries",
    doc="Global Registries owner surface for tenant education system attachments.",
)
WeatherLocation = _proxy_model(
    LegacyWeatherLocation,
    app_label="global_registries",
    doc="Global Registries owner surface for weather and location registry entries.",
)

__all__ = [
    "AcademicTerminologyRegistry",
    "CalendarSystemRegistry",
    "CountryRegistry",
    "CurrencyRegistry",
    "DocumentTypeRegistry",
    "EducationSystemProfile",
    "EducationLevelRegistry",
    "EducationSystemTypeRegistry",
    "FeeCategoryRegistry",
    "GradeScaleRegistry",
    "GradingScaleConfig",
    "HolidayCalendar",
    "InstitutionTypeRegistry",
    "LocaleRegistry",
    "Province",
    "RegionConfig",
    "SubdivisionRegistry",
    "SystemFeature",
    "TenantSystem",
    "TimeZoneRegistry",
    "WeatherLocation",
]
