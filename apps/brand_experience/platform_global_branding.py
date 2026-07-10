"""
Phase B Batch 1: first-class platform branding singleton in brand_experience.

Authoritative store for global theme packs, report defaults, and branding media
that previously lived only on the siteconfig tenant platform settings singleton row.
That slim row remains the compatibility write surface; saves sync into this row and
get_effective_site_settings merges this row over the legacy copy (see platform_runtime.helpers).
"""

from __future__ import annotations

from django.db import DatabaseError, models

from apps.siteconfig.image_utils import optimize_image
from apps.siteconfig.svg_sanitize import validate_svg_safe


class PlatformGlobalBranding(models.Model):
    """
    Singleton row (pk=1): platform-wide branding and report defaults.
    Mirrors the corresponding concrete fields on the slim tenant settings row for migration off siteconfig.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    video_background = models.FileField(
        upload_to="branding/video/",
        blank=True,
        null=True,
        help_text="Optional: Short looping video (mp4/webm) for animated background.",
    )
    svg_background = models.FileField(
        upload_to="branding/svg/",
        blank=True,
        null=True,
        help_text="Optional: SVG file for animated or vector background.",
        validators=[validate_svg_safe],
    )
    logo = models.ImageField(
        upload_to="branding/", blank=True, null=True,
        validators=[validate_svg_safe],
    )
    background_image = models.ImageField(
        upload_to="branding/bg/", blank=True, null=True,
        validators=[validate_svg_safe],
    )
    favicon = models.ImageField(
        upload_to="branding/",
        blank=True,
        null=True,
        help_text="Favicon for browser tabs. Shown across portal, backend, and admin.",
        validators=[validate_svg_safe],
    )
    sidebar_icon = models.ImageField(
        upload_to="branding/",
        blank=True,
        null=True,
        help_text="Optional small icon shown when the nav sidebar is collapsed.",
        validators=[validate_svg_safe],
    )
    theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_global_branding_portal",
        help_text="Theme for portal (parent, teacher, student dashboards).",
    )
    admin_theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_global_branding_admin",
        help_text="Theme for staff dashboards: /admin and /backend.",
    )
    teacher_theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_global_branding_teacher",
    )
    parent_theme_pack = models.ForeignKey(
        "siteconfig.ThemePack",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_global_branding_parent",
    )
    default_term_report_style = models.ForeignKey(
        "siteconfig.ReportCardStyle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_global_term_default",
    )
    default_annual_report_style = models.ForeignKey(
        "siteconfig.ReportCardStyle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_global_annual_default",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "brand_experience"
        verbose_name = "Platform global branding"
        verbose_name_plural = "Platform global branding"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1),
                name="brand_experience_platformglobalbranding_id_is_one",
            ),
        ]

    def _optimize_branding_assets(self) -> None:
        from django.db.models.fields.files import FieldFile

        for field_name in ("logo", "background_image", "favicon", "sidebar_icon"):
            field = getattr(self, field_name, None)
            if not isinstance(field, FieldFile) or not getattr(field, "name", None):
                continue
            try:
                file_handle = field.file
            except (FileNotFoundError, OSError, ValueError):
                continue
            if getattr(file_handle, "_optimized", False):
                continue
            optimized = optimize_image(field)
            if not optimized:
                continue
            optimized._optimized = True
            field.save(field.name, optimized, save=False)

    def save(self, *args, **kwargs):
        self.pk = 1
        self.id = 1
        self._optimize_branding_assets()
        super().save(*args, **kwargs)
        try:
            from apps.brand_experience.branding_singleton_sync import (
                mirror_platform_global_branding_fk_ids_to_runtime_payload,
            )

            mirror_platform_global_branding_fk_ids_to_runtime_payload()
        except (AttributeError, ImportError, TypeError, ValueError):
            pass
        try:
            from apps.platform_runtime.helpers import (
                invalidate_effective_site_settings_cache,
            )

            invalidate_effective_site_settings_cache()
        except (AttributeError, ImportError, TypeError, ValueError):
            pass
        try:
            from apps.platform_runtime.helpers import get_platform_site_settings_record
            from apps.platform_runtime.phase_b_domain_snapshots import (
                sync_phase_b_domain_snapshots_from_site,
            )

            # config-resolver-allow: row object is passed whole to sync_phase_b_domain_snapshots_from_site()
            site = get_platform_site_settings_record(create=False)
            if site is not None:
                sync_phase_b_domain_snapshots_from_site(site)
        except (AttributeError, ImportError, TypeError, ValueError, DatabaseError):
            pass
