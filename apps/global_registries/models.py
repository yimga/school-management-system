"""
Global registries bounded-context surface.

These state-compatible re-exports provide a stable domain import path while
storage ownership is still moving out of legacy apps.
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

__all__ = [
    "AcademicTerminologyRegistry",
    "CalendarSystemRegistry",
    "CountryRegistry",
    "CurrencyRegistry",
    "DocumentTypeRegistry",
    "EducationLevelRegistry",
    "EducationSystemTypeRegistry",
    "FeeCategoryRegistry",
    "GradeScaleRegistry",
    "InstitutionTypeRegistry",
    "LocaleRegistry",
    "SubdivisionRegistry",
    "TimeZoneRegistry",
]
