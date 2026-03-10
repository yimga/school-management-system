"""
Global Registries domain (plan Workstream B — seven bounded domains).
Region, education system, grading, AI registry, tenant system, etc.
Re-exports from .models. Import from here for new code.
"""
from .models import (
    AIModelRegistry,
    AIEmbeddingStore,
    CustomNuance,
    EducationSystemProfile,
    GlobalBrandRegistry,
    GradingScaleConfig,
    PendingNuance,
    Province,
    RegionalAIConfig,
    RegionConfig,
    SystemFeature,
    TenantAdmissionNumberPolicy,
    TenantSystem,
    WeatherLocation,
)

__all__ = [
    "RegionConfig",
    "EducationSystemProfile",
    "Province",
    "TenantSystem",
    "TenantAdmissionNumberPolicy",
    "GradingScaleConfig",
    "WeatherLocation",
    "RegionalAIConfig",
    "AIModelRegistry",
    "AIEmbeddingStore",
    "CustomNuance",
    "PendingNuance",
    "GlobalBrandRegistry",
    "SystemFeature",
]
