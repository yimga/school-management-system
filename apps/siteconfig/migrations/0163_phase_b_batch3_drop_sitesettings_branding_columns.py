# Phase B Batch 3: drop SiteSettings columns duplicated in PlatformGlobalBranding.

from django.db import migrations


def _ensure_pgb_from_sitesettings(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    PlatformGlobalBranding = apps.get_model(
        "brand_experience", "PlatformGlobalBranding"
    )
    site = SiteSettings.objects.order_by("pk").first()
    if site is None:
        return
    pgb, _ = PlatformGlobalBranding.objects.get_or_create(pk=1)
    for fname in (
        "video_background",
        "svg_background",
        "logo",
        "background_image",
        "favicon",
        "sidebar_icon",
    ):
        setattr(pgb, fname, getattr(site, fname, None))
    for id_attr in (
        "theme_pack_id",
        "admin_theme_pack_id",
        "teacher_theme_pack_id",
        "parent_theme_pack_id",
        "default_term_report_style_id",
        "default_annual_report_style_id",
    ):
        setattr(pgb, id_attr, getattr(site, id_attr, None))
    pgb.save()


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0162_phase_b_slim_sitesettings"),
        ("brand_experience", "0002_platform_global_branding"),
    ]

    operations = [
        migrations.RunPython(_ensure_pgb_from_sitesettings, migrations.RunPython.noop),
        migrations.RemoveField(model_name="sitesettings", name="video_background"),
        migrations.RemoveField(model_name="sitesettings", name="svg_background"),
        migrations.RemoveField(model_name="sitesettings", name="logo"),
        migrations.RemoveField(model_name="sitesettings", name="background_image"),
        migrations.RemoveField(model_name="sitesettings", name="favicon"),
        migrations.RemoveField(model_name="sitesettings", name="sidebar_icon"),
        migrations.RemoveField(model_name="sitesettings", name="theme_pack"),
        migrations.RemoveField(model_name="sitesettings", name="admin_theme_pack"),
        migrations.RemoveField(model_name="sitesettings", name="teacher_theme_pack"),
        migrations.RemoveField(model_name="sitesettings", name="parent_theme_pack"),
        migrations.RemoveField(
            model_name="sitesettings", name="default_term_report_style"
        ),
        migrations.RemoveField(
            model_name="sitesettings", name="default_annual_report_style"
        ),
    ]
