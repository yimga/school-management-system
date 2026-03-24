"""
Sync SiteSettings (compatibility write surface) <-> PlatformGlobalBranding (bounded context).
"""

from __future__ import annotations

from typing import Any

# Field names shared between SiteSettings (slim) and PlatformGlobalBranding.
_BRANDING_MIRROR_FIELDS: tuple[str, ...] = (
    "video_background",
    "svg_background",
    "logo",
    "background_image",
    "favicon",
    "sidebar_icon",
    "theme_pack_id",
    "admin_theme_pack_id",
    "teacher_theme_pack_id",
    "parent_theme_pack_id",
    "default_term_report_style_id",
    "default_annual_report_style_id",
)


def get_platform_global_branding():
    try:
        from apps.brand_experience.platform_global_branding import PlatformGlobalBranding

        return PlatformGlobalBranding.objects.filter(pk=1).first()
    except Exception:
        return None


def sync_platform_branding_row_from_sitesettings(site: Any) -> None:
    """
    After SiteSettings.save, copy concrete branding/report-default columns into
    PlatformGlobalBranding(pk=1). Uses DB state via refresh_from_db.
    """
    if site is None or not getattr(site, "pk", None):
        return
    try:
        site.refresh_from_db()
    except Exception:
        return

    try:
        from apps.brand_experience.platform_global_branding import PlatformGlobalBranding
    except ImportError:
        return

    updates = {}
    for name in _BRANDING_MIRROR_FIELDS:
        if hasattr(site, name):
            updates[name] = getattr(site, name)

    if not updates:
        return

    obj, _created = PlatformGlobalBranding.objects.get_or_create(pk=1)
    for key, val in updates.items():
        setattr(obj, key, val)
    obj.save()


def merge_platform_global_branding_into_base(base: Any) -> None:
    """
    Overlay PlatformGlobalBranding onto the shallow SiteSettings copy used by
    get_effective_site_settings. Call after RuntimeDefaults payload merge.
    """
    row = get_platform_global_branding()
    if row is None:
        return
    for name in _BRANDING_MIRROR_FIELDS:
        val = getattr(row, name, None)
        try:
            object.__setattr__(base, name, val)
        except (TypeError, AttributeError):
            try:
                setattr(base, name, val)
            except (TypeError, AttributeError):
                pass


def mirror_platform_global_branding_fk_ids_to_runtime_payload() -> None:
    """
    Keep RuntimeDefaults.payload theme/report id keys aligned with PGB so
    SiteSettings.owned_payload and domain snapshots stay consistent after Batch 3.
    """
    row = get_platform_global_branding()
    if row is None:
        return
    updates = {}
    for name in (
        "theme_pack_id",
        "admin_theme_pack_id",
        "teacher_theme_pack_id",
        "parent_theme_pack_id",
        "default_term_report_style_id",
        "default_annual_report_style_id",
    ):
        updates[name] = getattr(row, name, None)
    try:
        from apps.siteconfig.models import SiteSettings

        SiteSettings._persist_runtime_payload_updates(updates)
    except (AttributeError, ImportError, TypeError, ValueError):
        pass
