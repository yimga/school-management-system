# Phase B Batch 1: bounded-context singleton for platform branding (GAP.12 physical step).

import django.db.models.deletion
from django.db import migrations, models


def backfill_from_sitesettings(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    PlatformGlobalBranding = apps.get_model("brand_experience", "PlatformGlobalBranding")
    site = SiteSettings.objects.order_by("pk").first()
    if site is None:
        return
    defaults = {
        "theme_pack_id": getattr(site, "theme_pack_id", None),
        "admin_theme_pack_id": getattr(site, "admin_theme_pack_id", None),
        "teacher_theme_pack_id": getattr(site, "teacher_theme_pack_id", None),
        "parent_theme_pack_id": getattr(site, "parent_theme_pack_id", None),
        "default_term_report_style_id": getattr(
            site, "default_term_report_style_id", None
        ),
        "default_annual_report_style_id": getattr(
            site, "default_annual_report_style_id", None
        ),
    }
    for fname in (
        "video_background",
        "svg_background",
        "logo",
        "background_image",
        "favicon",
        "sidebar_icon",
    ):
        defaults[fname] = getattr(site, fname, None) or None
    PlatformGlobalBranding.objects.update_or_create(pk=1, defaults=defaults)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("brand_experience", "0001_proxy_owner_models"),
        ("siteconfig", "0162_phase_b_slim_sitesettings"),
    ]

    operations = [
        migrations.CreateModel(
            name="PlatformGlobalBranding",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "video_background",
                    models.FileField(
                        blank=True,
                        help_text="Optional: Short looping video (mp4/webm) for animated background.",
                        null=True,
                        upload_to="branding/video/",
                    ),
                ),
                (
                    "svg_background",
                    models.FileField(
                        blank=True,
                        help_text="Optional: SVG file for animated or vector background.",
                        null=True,
                        upload_to="branding/svg/",
                    ),
                ),
                (
                    "logo",
                    models.ImageField(
                        blank=True, null=True, upload_to="branding/"
                    ),
                ),
                (
                    "background_image",
                    models.ImageField(
                        blank=True, null=True, upload_to="branding/bg/"
                    ),
                ),
                (
                    "favicon",
                    models.ImageField(
                        blank=True,
                        help_text="Favicon for browser tabs. Shown across portal, backend, and admin.",
                        null=True,
                        upload_to="branding/",
                    ),
                ),
                (
                    "sidebar_icon",
                    models.ImageField(
                        blank=True,
                        help_text="Optional small icon shown when the nav sidebar is collapsed.",
                        null=True,
                        upload_to="branding/",
                    ),
                ),
                (
                    "theme_pack",
                    models.ForeignKey(
                        blank=True,
                        help_text="Theme for portal (parent, teacher, student dashboards).",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_global_branding_portal",
                        to="siteconfig.themepack",
                    ),
                ),
                (
                    "admin_theme_pack",
                    models.ForeignKey(
                        blank=True,
                        help_text="Theme for staff dashboards: /admin and /backend.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_global_branding_admin",
                        to="siteconfig.themepack",
                    ),
                ),
                (
                    "teacher_theme_pack",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_global_branding_teacher",
                        to="siteconfig.themepack",
                    ),
                ),
                (
                    "parent_theme_pack",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_global_branding_parent",
                        to="siteconfig.themepack",
                    ),
                ),
                (
                    "default_term_report_style",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_global_term_default",
                        to="siteconfig.reportcardstyle",
                    ),
                ),
                (
                    "default_annual_report_style",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="platform_global_annual_default",
                        to="siteconfig.reportcardstyle",
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Platform global branding",
                "verbose_name_plural": "Platform global branding",
            },
        ),
        migrations.AddConstraint(
            model_name="platformglobalbranding",
            constraint=models.CheckConstraint(
                condition=models.Q(id=1),
                name="brand_experience_platformglobalbranding_id_is_one",
            ),
        ),
        migrations.RunPython(backfill_from_sitesettings, noop_reverse),
    ]
