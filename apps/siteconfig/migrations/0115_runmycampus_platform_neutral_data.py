# RunMyCampus branding: set platform-neutral defaults on existing data
# (SiteSettings singleton and ReportCardStyle watermark_text where Gilead)

from django.db import migrations


def site_settings_platform_neutral(apps, schema_editor):
    SiteSettings = apps.get_model("siteconfig", "SiteSettings")
    for obj in SiteSettings.objects.all():
        updated = False
        if obj.site_name and "gilead" in (obj.site_name or "").lower():
            obj.site_name = "RunMyCampus"
            updated = True
        if (
            obj.report_preview_footer_note
            and "gilead" in (obj.report_preview_footer_note or "").lower()
        ):
            obj.report_preview_footer_note = "Powered by RunMyCampus."
            updated = True
        if updated:
            obj.save(update_fields=["site_name", "report_preview_footer_note"])


def reportcard_style_watermark_neutral(apps, schema_editor):
    ReportCardStyle = apps.get_model("siteconfig", "ReportCardStyle")
    ReportCardStyle.objects.filter(watermark_text__icontains="gilead").update(
        watermark_text="RunMyCampus"
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("siteconfig", "0114_add_global_brand_registry"),
    ]

    operations = [
        migrations.RunPython(site_settings_platform_neutral, noop),
        migrations.RunPython(reportcard_style_watermark_neutral, noop),
    ]
