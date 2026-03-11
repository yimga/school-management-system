"""
Brand experience bounded-context ownership surface.

These are proxy-owner models over the legacy storage tables so new code can
import from `apps.brand_experience` immediately while data ownership is still
being migrated out of `apps.siteconfig`.
"""

from apps.siteconfig.models import (
    BrandProfile as LegacyBrandProfile,
    BrandSettings as LegacyBrandSettings,
    DesignTemplate as LegacyDesignTemplate,
    GlobalBrandRegistry as LegacyGlobalBrandRegistry,
    ThemePack as LegacyThemePack,
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


ThemePack = _proxy_model(
    LegacyThemePack,
    app_label="brand_experience",
    doc="Brand Experience owner surface for portal/admin/student theme packs.",
)
DesignTemplate = _proxy_model(
    LegacyDesignTemplate,
    app_label="brand_experience",
    doc="Brand Experience owner surface for reusable document and experience templates.",
)
BrandProfile = _proxy_model(
    LegacyBrandProfile,
    app_label="brand_experience",
    doc="Brand Experience owner surface for tenant brand profiles.",
)
BrandSettings = _proxy_model(
    LegacyBrandSettings,
    app_label="brand_experience",
    doc="Brand Experience owner surface for tenant brand settings.",
)
GlobalBrandRegistry = _proxy_model(
    LegacyGlobalBrandRegistry,
    app_label="brand_experience",
    doc="Brand Experience owner surface for globally seeded branding assets.",
)

__all__ = [
    "ThemePack",
    "DesignTemplate",
    "BrandProfile",
    "BrandSettings",
    "GlobalBrandRegistry",
]
